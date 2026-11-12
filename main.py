import pygame
import random
import math
import json
import os
import sys
from collections import deque

# ============================================================
# DRONE HUNTER v5.38
# Weapon update: pulse rifle and explosive rocket launcher
# Python + Pygame
# ============================================================

pygame.init()

WIDTH, HEIGHT = 1100, 720
FPS = 60
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("DRONE HUNTER v5.38 - BOSS VISUALS")
CLOCK = pygame.time.Clock()

# -------------------- COLORS --------------------

BLACK = (5, 7, 11)
BG = (8, 11, 17)
ROOM = (17, 21, 28)
GRID = (25, 31, 39)
WALL = (55, 62, 72)
WHITE = (222, 229, 232)
LIGHT = (139, 151, 162)
RED = (224, 55, 48)
DARK_RED = (83, 22, 25)
ORANGE = (235, 125, 42)
YELLOW = (241, 190, 55)
GREEN = (72, 190, 112)
BLUE = (57, 131, 213)
PURPLE = (151, 78, 192)
CYAN = (57, 198, 210)

FONT = pygame.font.SysFont("consolas", 20)
SMALL = pygame.font.SysFont("consolas", 15)
TINY = pygame.font.SysFont("consolas", 11)
MEDIUM = pygame.font.SysFont("consolas", 27, bold=True)
BIG = pygame.font.SysFont("consolas", 52, bold=True)

ROOM_X, ROOM_Y = 55, 92
ROOM_W, ROOM_H = 820, 570
WALL_SIZE = 24

TOTAL_LEVELS = 10
MIN_ROOMS_PER_LEVEL = 6
MAX_ROOMS_PER_LEVEL = 10

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(BASE_DIR, "save.json")
PROFILE_FILE = os.path.join(BASE_DIR, "pilot_profile.json")
CRASH_LOG = os.path.join(BASE_DIR, "crash_log.txt")


# ============================================================
# HELPERS
# ============================================================

def text(surface, value, font, color, x, y, center=False):
    img = font.render(str(value), True, color)
    rect = img.get_rect()
    rect.center = (x, y) if center else rect.center
    if not center:
        rect.topleft = (x, y)
    surface.blit(img, rect)


def clamp(v, low, high):
    return max(low, min(high, v))


def separate_enemies(enemies, obstacle_check=None):
    """Раздвигает дронов, не проталкивая их сквозь укрытия."""
    active = [e for e in enemies if not e.dead]
    if len(active) < 2:
        return

    def move_safely(enemy, dx, dy):
        nx = clamp(enemy.x + dx, ROOM_X + WALL_SIZE + enemy.radius,
                   ROOM_X + ROOM_W - WALL_SIZE - enemy.radius)
        ny = clamp(enemy.y + dy, ROOM_Y + WALL_SIZE + enemy.radius,
                   ROOM_Y + ROOM_H - WALL_SIZE - enemy.radius)
        # Разделение толпы выполняется по осям отдельно: если одна сторона
        # упирается в укрытие, вторая всё ещё может освободить проход.
        if obstacle_check is None or not obstacle_check(nx, enemy.y, enemy.radius):
            enemy.x = nx
        if obstacle_check is None or not obstacle_check(enemy.x, ny, enemy.radius):
            enemy.y = ny

    # Несколько мягких проходов раздвигают толпу без резких телепортаций.
    for _ in range(4):
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                dx = b.x - a.x
                dy = b.y - a.y
                distance = math.hypot(dx, dy)
                minimum = a.radius + b.radius + 9
                if distance >= minimum:
                    continue
                if distance < 0.001:
                    angle = ((i + 1) * 2.399963229728653) % math.tau
                    dx, dy = math.cos(angle), math.sin(angle)
                    distance = 1.0
                overlap = (minimum - distance) * 0.30
                nx, ny = dx / distance, dy / distance
                # Тяжёлые дроны и щитоносцы сильнее удерживают позицию.
                a_weight = 0.65 if a.kind in ("heavy", "shield") else 1.0
                b_weight = 0.65 if b.kind in ("heavy", "shield") else 1.0
                total = a_weight + b_weight
                move_safely(a, -nx * overlap * (b_weight / total) * 2,
                            -ny * overlap * (b_weight / total) * 2)
                move_safely(b, nx * overlap * (a_weight / total) * 2,
                            ny * overlap * (a_weight / total) * 2)


def dist(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)


def circle_hit(a_x, a_y, a_r, b_x, b_y, b_r):
    return dist(a_x, a_y, b_x, b_y) <= a_r + b_r


# ============================================================
# PARTICLES
# ============================================================

class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.vx = random.uniform(-100, 100)
        self.vy = random.uniform(-100, 100)
        self.life = random.uniform(.25, .65)
        self.max_life = self.life
        self.color = color
        self.size = random.randint(2, 5)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= .96
        self.vy *= .96
        self.life -= dt

    def draw(self, surface):
        if self.life <= 0:
            return
        ratio = self.life / self.max_life
        size = max(1, int(self.size * ratio))
        pygame.draw.circle(surface, self.color,
                           (int(self.x), int(self.y)), size)


class Shockwave:
    """Короткое расширяющееся кольцо для попаданий и уничтожения дронов."""
    def __init__(self, x, y, color, max_radius=46, duration=.24, width=3):
        self.x = x
        self.y = y
        self.color = color
        self.max_radius = max_radius
        self.duration = duration
        self.life = duration
        self.width = width

    def update(self, dt):
        self.life -= dt

    def draw(self, surface):
        if self.life <= 0:
            return
        progress = 1 - self.life / self.duration
        radius = max(1, int(4 + (self.max_radius - 4) * progress))
        fade = max(.15, self.life / self.duration)
        color = tuple(max(0, min(255, int(c * fade))) for c in self.color)
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), radius, self.width)


# ============================================================
# BULLET
# ============================================================

class Bullet:
    def __init__(self, x, y, dx, dy, damage, enemy=False, speed=700,
                 color=None, radius=4, element="normal", pierce=0,
                 explosive_radius=0):
        self.x = x
        self.y = y
        # Храним предыдущую позицию, чтобы рисовать короткий след за пулей.
        self.prev_x = x
        self.prev_y = y
        length = math.hypot(dx, dy) or 1
        self.vx = dx / length * speed
        self.vy = dy / length * speed
        self.damage = damage
        self.enemy = enemy
        self.life = 1.4
        self.radius = radius
        self.color = color or (RED if enemy else ORANGE)
        self.element = element
        self.pierce = max(0, int(pierce))
        self.hit_targets = set()
        self.chain_used = False
        self.explosive_radius = max(0, int(explosive_radius))

    def update(self, dt):
        self.prev_x, self.prev_y = self.x, self.y
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def alive(self):
        return (
            self.life > 0
            and ROOM_X - 50 < self.x < ROOM_X + ROOM_W + 50
            and ROOM_Y - 50 < self.y < ROOM_Y + ROOM_H + 50
        )

    def draw(self, surface):
        # Яркое ядро и короткий цветной след делают направление выстрела понятнее.
        tail_x = self.x - self.vx * 0.025
        tail_y = self.y - self.vy * 0.025
        tail_color = self.color if self.enemy else tuple(max(0, int(c * 0.55)) for c in self.color)
        pygame.draw.line(surface, tail_color,
                         (int(tail_x), int(tail_y)),
                         (int(self.x), int(self.y)), max(1, self.radius))
        pygame.draw.circle(surface, self.color,
                           (int(self.x), int(self.y)), self.radius)
        if not self.enemy:
            pygame.draw.circle(surface, (255, 235, 180),
                               (int(self.x), int(self.y)), max(1, self.radius // 2))


# ============================================================
# SCRAP / MEDKIT / EXIT
# ============================================================

class Scrap:
    def __init__(self, x, y, amount=None):
        self.x = x
        self.y = y
        self.amount = amount or random.randint(1, 3)
        self.phase = random.random() * 6

    def update(self, dt):
        self.phase += dt * 5

    def attract_to(self, target_x, target_y, dt):
        # Запчасти начинают притягиваться к игроку, когда он подходит близко.
        dx, dy = target_x - self.x, target_y - self.y
        distance = math.hypot(dx, dy)
        if 35 < distance < 150:
            strength = 220 + (150 - distance) * 1.8
            self.x += dx / max(1, distance) * strength * dt
            self.y += dy / max(1, distance) * strength * dt

    def draw(self, surface):
        # Крупные стопки заметнее: размер отражает количество запчастей.
        r = 7 + min(3, max(0, self.amount - 1) // 2) + int(math.sin(self.phase) * 2)
        # Мягкое свечение помогает замечать выпавшие запчасти в тёмных комнатах.
        glow = pygame.Surface((r * 5, r * 5), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 210, 55, 28), (r * 2, r * 2), r * 2)
        surface.blit(glow, (int(self.x-r*2), int(self.y-r*2)))
        pygame.draw.rect(surface, YELLOW,
                         (int(self.x-r), int(self.y-r), r*2, r*2))
        pygame.draw.line(surface, BLACK,
                         (int(self.x-r//2), int(self.y)),
                         (int(self.x+r//2), int(self.y)), 2)
        # Количество показываем только на крупных стопках, чтобы не захламлять пол.
        if self.amount >= 4:
            badge = pygame.Rect(int(self.x + r - 3), int(self.y - r - 3), 15, 12)
            pygame.draw.rect(surface, BLACK, badge, border_radius=3)
            text(surface, str(self.amount), TINY, YELLOW,
                 badge.centerx, badge.centery, True)


class Medkit:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.phase = 0

    def update(self, dt):
        self.phase += dt * 4

    def draw(self, surface):
        r = 12 + int(math.sin(self.phase) * 1)
        pygame.draw.rect(surface, WHITE,
                         (int(self.x-r), int(self.y-r), r*2, r*2),
                         border_radius=3)
        pygame.draw.rect(surface, RED,
                         (int(self.x-3), int(self.y-8), 6, 16))
        pygame.draw.rect(surface, RED,
                         (int(self.x-8), int(self.y-3), 16, 6))


# ============================================================
# ENEMY
# ============================================================

ENEMY_DATA = {
    "scout": {
        "hp": 2, "speed": 135, "damage": 7, "radius": 17,
        "color": BLUE, "scrap": (1, 2)
    },
    "kamikaze": {
        "hp": 3, "speed": 175, "damage": 30, "radius": 18,
        "color": ORANGE, "scrap": (1, 3)
    },
    "gunner": {
        "hp": 6, "speed": 72, "damage": 10, "radius": 20,
        "color": PURPLE, "scrap": (2, 4)
    },
    "robot": {
        "hp": 9, "speed": 58, "damage": 13, "radius": 22,
        "color": RED, "scrap": (2, 5)
    },
    "sniper": {
        "hp": 5, "speed": 45, "damage": 24, "radius": 19,
        "color": (80, 180, 255), "scrap": (3, 6)
    },
    "lancer": {
        "hp": 8, "speed": 52, "damage": 15, "radius": 21,
        "color": (235, 90, 220), "scrap": (3, 6)
    },
    "shield": {
        "hp": 13, "speed": 48, "damage": 11, "radius": 25,
        "color": (90, 220, 170), "scrap": (3, 7)
    },
    "heavy": {
        "hp": 20, "speed": 38, "damage": 18, "radius": 28,
        "color": (210, 150, 70), "scrap": (4, 8)
    },
}


class Enemy:
    def __init__(self, kind, x, y, difficulty=1):
        d = ENEMY_DATA[kind]
        self.kind = kind
        self.x = x
        self.y = y
        self.radius = d["radius"]
        self.color = d["color"]
        # Рост сложности заметнее на поздних уровнях, но остаётся ограниченным
        # диапазоном уровней игры (1–10), чтобы враги не превращались в губки для пуль.
        level = max(1, min(10, int(difficulty)))
        hp_scale = 1.0 + level * 0.12 + level * level * 0.008
        damage_scale = 1.0 + level * 0.055
        speed_scale = 1.0 + level * 0.022
        self.max_hp = max(1, int(round(d["hp"] * hp_scale)))
        self.hp = self.max_hp
        self.speed = d["speed"] * speed_scale
        self.damage = max(1, int(round(d["damage"] * damage_scale)))
        self.shoot_timer = random.uniform(.4, 1.4)
        self.stun = 0
        self.dead = False
        self.burn_timer = 0.0
        self.burn_tick = 0.0
        self.burn_damage = 0
        self.hit_flash = 0
        self.hit_pulse = 0.0
        self.orbit = random.choice([-1, 1])
        self.ability_timer = random.uniform(1.5, 3.0)
        self.charge_timer = random.uniform(2.5, 5.0)
        self.heavy_windup = 0.0
        self.heavy_burst = 0.0
        self.shield_timer = random.uniform(1.0, 2.5)
        self.shield_active = kind == "shield"
        self.aim_dir = (1.0, 0.0)
        # Лансер фиксирует позицию игрока и заряжает направленный энергетический залп.
        self.lance_windup = 0.0
        self.lance_angle = 0.0
        self.lance_target_x = float(x)
        self.lance_target_y = float(y)
        # Камикадзе предупреждает о рывке, прежде чем резко ускориться.
        self.charge_windup = 0.0
        self.charge_burst = 0.0
        self.charge_cooldown = random.uniform(1.2, 2.2)
        # Время анимации используется для вращения лопастей и лёгкого покачивания.
        self.anim_time = random.random() * math.tau
        self.tactic_timer = random.uniform(2.0, 3.8)
        # Короткий кэш маршрута снижает повторные BFS-поиски и рывки у укрытий.
        self.path_cache_timer = 0.0
        self.path_cache_waypoint = None

    def update(self, player, bullets, dt, level, allies=None):
        if self.dead:
            return

        self.hit_flash = max(0, self.hit_flash - dt)
        self.hit_pulse = max(0.0, self.hit_pulse - dt)
        self.anim_time += dt * (1.0 if self.stun > 0 else 1.0 + self.speed / 180.0)
        self.tactic_timer -= dt
        if self.tactic_timer <= 0:
            self.orbit *= -1
            self.tactic_timer = random.uniform(2.0, 3.8)
        # Кэш маршрута сохраняется между кадрами и сбрасывается после достижения точки.
        # Это не даёт врагу каждый кадр выбирать новую точку обхода.

        dx = player.x - self.x
        dy = player.y - self.y
        d = math.hypot(dx, dy) or 1
        # Aim direction is also used by the visual warning before ranged attacks.
        self.aim_dir = (dx / d, dy / d)

        if self.stun > 0:
            self.stun -= dt
            return

        if self.kind == "scout":
            # Разведчик не просто бежит по прямой: на близкой дистанции
            # начинает смещаться вбок, заставляя игрока корректировать прицел.
            if d > 155:
                move_x, move_y = dx / d, dy / d
            else:
                side_x, side_y = -dy / d * self.orbit, dx / d * self.orbit
                move_x = dx / d * 0.25 + side_x * 0.9
                move_y = dy / d * 0.25 + side_y * 0.9
            self.x += move_x * self.speed * dt
            self.y += move_y * self.speed * dt

        elif self.kind == "kamikaze":
            # Сначала короткая телеграфируемая подготовка, затем быстрый рывок.
            # Если рядом есть щитоносец или стрелок, камикадзе подходит по дуге,
            # пытаясь зайти сбоку, вместо того чтобы выстраиваться в одну линию.
            self.charge_cooldown = max(0.0, self.charge_cooldown - dt)
            nearby_support = False
            vulnerable_support = False
            if allies:
                nearby_support = any(
                    a is not self and not a.dead
                    and a.kind in ("shield", "gunner", "robot", "sniper", "lancer", "heavy")
                    and dist(self.x, self.y, a.x, a.y) < 250
                    for a in allies
                )
                # Когда рядом ранен союзник, камикадзе активнее пытается зайти сбоку,
                # пока игрок может быть занят атакой другого противника.
                vulnerable_support = any(
                    a is not self and not a.dead
                    and a.kind in ("gunner", "robot", "sniper", "lancer", "heavy")
                    and a.hp / max(1, a.max_hp) < 0.55
                    and dist(self.x, self.y, a.x, a.y) < 300
                    for a in allies
                )
            if self.charge_windup > 0:
                self.charge_windup = max(0.0, self.charge_windup - dt)
                # Во время подготовки дрон замедляется, давая игроку шанс уклониться.
                self.x += dx / d * self.speed * 0.22 * dt
                self.y += dy / d * self.speed * 0.22 * dt
                if self.charge_windup <= 0:
                    self.charge_burst = 0.48
                    self.charge_cooldown = 2.0
            elif self.charge_burst > 0:
                self.charge_burst = max(0.0, self.charge_burst - dt)
                self.x += dx / d * self.speed * 3.1 * dt
                self.y += dy / d * self.speed * 3.1 * dt
            else:
                if (nearby_support or vulnerable_support) and d > 100:
                    # Боковой обход становится выраженнее, когда рядом ранен стрелок:
                    # камикадзе старается давить с фланга, пока игрок занят другой целью.
                    side_x, side_y = -dy / d * self.orbit, dx / d * self.orbit
                    side_strength = 0.98 if vulnerable_support else 0.78
                    forward_strength = 0.68 if vulnerable_support else 0.72
                    move_x = dx / d * forward_strength + side_x * side_strength
                    move_y = dy / d * forward_strength + side_y * side_strength
                    move_len = math.hypot(move_x, move_y) or 1.0
                    self.x += move_x / move_len * self.speed * dt
                    self.y += move_y / move_len * self.speed * dt
                else:
                    self.x += dx / d * self.speed * dt
                    self.y += dy / d * self.speed * dt
                if d < 245 and self.charge_cooldown <= 0:
                    self.charge_windup = 0.48

        elif self.kind == "gunner":
            # Стрелок старается держать дистанцию, а если игрок врывается близко,
            # резко смещается вбок, чтобы не оставаться лёгкой мишенью.
            desired = 280
            if d < 175:
                move = -1.15
                side_strength = 1.05
            elif d < 230:
                move = -0.75
                side_strength = 0.75
            else:
                move = 1 if d > desired else -1
                side_strength = 0.45
            px, py = -dy / d * self.orbit, dx / d * self.orbit
            move_x = dx/d * move + px * side_strength
            move_y = dy/d * move + py * side_strength
            move_len = math.hypot(move_x, move_y) or 1.0
            speed_factor = 1.35 if d < 175 else 1.0
            self.x += move_x / move_len * self.speed * speed_factor * dt
            self.y += move_y / move_len * self.speed * speed_factor * dt

            self.shoot_timer -= dt
            if self.shoot_timer <= 0 and d < 550:
                bullets.append(
                    Bullet(self.x, self.y, dx, dy,
                           self.damage, True, 440, RED, 5)
                )
                self.shoot_timer = max(.62, 1.4 - level*.065)

        elif self.kind == "robot":
            # Робот держит дистанцию и постоянно смещается вбок,
            # поэтому игроку сложнее стоять на месте и стрелять в одну точку.
            move = 1 if d > 310 else (-0.65 if d < 205 else 0.0)
            side_x, side_y = -dy / d * self.orbit, dx / d * self.orbit
            move_x = dx / d * move + side_x * 0.48
            move_y = dy / d * move + side_y * 0.48
            self.x += move_x * self.speed * dt
            self.y += move_y * self.speed * dt

            self.shoot_timer -= dt
            if self.shoot_timer <= 0 and d < 500:
                # Тройная очередь.
                angle = math.atan2(dy, dx)
                for spread in (-.12, 0, .12):
                    a = angle + spread
                    bullets.append(
                        Bullet(self.x, self.y,
                               math.cos(a), math.sin(a),
                               self.damage, True, 400, RED, 5)
                    )
                self.shoot_timer = max(.85, 1.8 - level*.065)

        elif self.kind == "sniper":
            # Снайпер держит дальнюю позицию. Если игрок прорвался близко,
            # он быстрее отступает и смещается вбок, пытаясь восстановить дистанцию.
            self.aim_dir = (dx / d, dy / d)
            desired = 420
            if d < 235:
                move = -1.65
                side_strength = 0.9
                speed_factor = 1.35
            elif d < 330:
                move = -1.0
                side_strength = 0.55
                speed_factor = 1.0
            else:
                move = 1 if d > desired else -0.8
                side_strength = 0.3
                speed_factor = 1.0
            px, py = -dy / d * self.orbit, dx / d * self.orbit
            move_x = dx/d * move + px * side_strength
            move_y = dy/d * move + py * side_strength
            move_len = math.hypot(move_x, move_y) or 1.0
            self.x += move_x / move_len * self.speed * speed_factor * dt
            self.y += move_y / move_len * self.speed * speed_factor * dt
            self.shoot_timer -= dt
            if self.shoot_timer <= 0 and d < 700:
                bullets.append(Bullet(self.x, self.y, dx, dy,
                                      self.damage, True, 260, (80, 180, 255), 8))
                self.shoot_timer = max(1.35, 3.0 - level*.10)

        elif self.kind == "lancer":
            # Лансер старается держать среднюю дистанцию и заряжает точный залп.
            # Координаты игрока фиксируются в начале зарядки, поэтому выстрел не самонаводится.
            desired = 365
            if d < 255:
                move = -1.0
                side_strength = 0.72
            elif d > desired:
                move = 0.72
                side_strength = 0.48
            else:
                move = 0.0
                side_strength = 0.62
            side_x, side_y = -dy / d * self.orbit, dx / d * self.orbit
            move_x = dx / d * move + side_x * side_strength
            move_y = dy / d * move + side_y * side_strength
            move_len = math.hypot(move_x, move_y) or 1.0
            self.x += move_x / move_len * self.speed * dt
            self.y += move_y / move_len * self.speed * dt

            if self.lance_windup > 0:
                self.lance_windup = max(0.0, self.lance_windup - dt)
                if self.lance_windup <= 0:
                    shot_angle = math.atan2(self.lance_target_y - self.y,
                                            self.lance_target_x - self.x)
                    shot_count = 5 if level >= 8 else 3
                    spread = 0.15 if shot_count == 5 else 0.10
                    for i in range(shot_count):
                        offset = (i - (shot_count - 1) / 2) * spread
                        angle = shot_angle + offset
                        bullets.append(Bullet(
                            self.x, self.y, math.cos(angle), math.sin(angle),
                            self.damage, True, 520, (245, 90, 230), 6
                        ))
                    self.shoot_timer = max(1.45, 2.5 - level * 0.075)
            else:
                self.shoot_timer -= dt
                if self.shoot_timer <= 0 and d < 720:
                    self.lance_target_x = float(player.x)
                    self.lance_target_y = float(player.y)
                    self.lance_angle = math.atan2(
                        self.lance_target_y - self.y,
                        self.lance_target_x - self.x
                    )
                    self.lance_windup = 0.72

        elif self.kind == "shield":
            # Щитоносец прикрывает ближайшего стрелка: старается занять позицию
            # между игроком и союзником, а не просто бежать на игрока по прямой.
            ranged_kinds = ("gunner", "robot", "sniper", "lancer", "heavy")
            guarded = None
            if allies:
                candidates = [a for a in allies
                              if a is not self and not a.dead and a.kind in ranged_kinds
                              and dist(self.x, self.y, a.x, a.y) < 360]
                if candidates:
                    # Не только ближайший: повреждённый стрелок получает приоритет,
                    # чтобы щитоносец помогал союзнику, которому грозит скорое уничтожение.
                    def guard_priority(ally):
                        distance = dist(self.x, self.y, ally.x, ally.y)
                        health_ratio = ally.hp / max(1, ally.max_hp)
                        wounded_bonus = 115 * (1.0 - health_ratio)
                        critical_bonus = 75 if health_ratio < 0.40 else 0
                        return distance - wounded_bonus - critical_bonus
                    guarded = min(candidates, key=guard_priority)

            if guarded is not None:
                ax, ay = player.x - guarded.x, player.y - guarded.y
                ad = math.hypot(ax, ay) or 1
                # Если союзник ранен, щитоносец занимает позицию ещё ближе к нему.
                guarded_ratio = guarded.hp / max(1, guarded.max_hp)
                guard_gap = 12 if guarded_ratio < 0.40 else 18
                target_x = guarded.x + ax / ad * (guarded.radius + self.radius + guard_gap)
                target_y = guarded.y + ay / ad * (guarded.radius + self.radius + guard_gap)
                tx, ty = target_x - self.x, target_y - self.y
                td = math.hypot(tx, ty) or 1
                if td > 12:
                    self.x += tx / td * self.speed * 1.12 * dt
                    self.y += ty / td * self.speed * 1.12 * dt
            else:
                self.x += dx / d * self.speed * dt
                self.y += dy / d * self.speed * dt

            self.shield_timer -= dt
            if self.shield_timer <= 0:
                self.shield_active = not self.shield_active
                self.shield_timer = 2.0 if self.shield_active else 2.2
            self.shoot_timer -= dt
            if self.shoot_timer <= 0 and d < 390:
                angle = math.atan2(dy, dx)
                bullets.append(Bullet(self.x, self.y, math.cos(angle), math.sin(angle),
                                      self.damage, True, 340, (90, 220, 170), 5))
                self.shoot_timer = 1.35

        elif self.kind == "heavy":
            # Тяжёлый дрон пытается перехватить игрока, а не просто
            # бесконечно идти следом. Боковой заход меняется по таймеру.
            self.charge_timer -= dt
            move_speed = self.speed
            if self.heavy_windup > 0:
                # Предупреждение перед рывком: тяжёлый дрон почти останавливается.
                self.heavy_windup = max(0.0, self.heavy_windup - dt)
                move_speed = self.speed * 0.12
                if self.heavy_windup <= 0:
                    self.heavy_burst = 0.42
                    self.charge_timer = 3.6
            elif self.heavy_burst > 0:
                # Во время рывка сохраняется направление на игрока.
                self.heavy_burst = max(0.0, self.heavy_burst - dt)
                move_speed = self.speed * 3.4
                self.x += dx / d * move_speed * dt
                self.y += dy / d * move_speed * dt
            elif self.charge_timer <= 0:
                self.heavy_windup = 0.58
                move_speed = self.speed * 0.12
                # Небольшая смена стороны делает следующий перехват менее предсказуемым.
                self.orbit *= -1
            else:
                # На средней дистанции тяжёлый дрон движется по диагонали,
                # пытаясь перекрыть путь. Вблизи идёт прямо, чтобы не кружить вокруг.
                if d > 145:
                    side_x, side_y = -dy / d * self.orbit, dx / d * self.orbit
                    toward = 0.78
                    sideways = 0.62 if d < 360 else 0.35
                    move_x = dx / d * toward + side_x * sideways
                    move_y = dy / d * toward + side_y * sideways
                    move_len = math.hypot(move_x, move_y) or 1.0
                    self.x += move_x / move_len * move_speed * dt
                    self.y += move_y / move_len * move_speed * dt
                else:
                    self.x += dx / d * move_speed * dt
                    self.y += dy / d * move_speed * dt
            self.shoot_timer -= dt
            if self.shoot_timer <= 0 and d < 430:
                angle = math.atan2(dy, dx)
                for spread in (-.22, -.07, .07, .22):
                    a = angle + spread
                    bullets.append(Bullet(self.x, self.y, math.cos(a), math.sin(a),
                                          self.damage, True, 330, (210, 150, 70), 6))
                self.shoot_timer = 2.1

        self.x = clamp(self.x,
                       ROOM_X + WALL_SIZE + self.radius,
                       ROOM_X + ROOM_W - WALL_SIZE - self.radius)
        self.y = clamp(self.y,
                       ROOM_Y + WALL_SIZE + self.radius,
                       ROOM_Y + ROOM_H - WALL_SIZE - self.radius)

    def draw(self, surface):
        # У каждого типа врага собственный силуэт, чтобы их было проще различать.
        # Небольшое покачивание и тень отделяют роботов от металлического пола.
        bob = int(round(math.sin(self.anim_time * 3.2) * 1.5))
        x, y, r = int(self.x), int(self.y + bob), self.radius
        color = WHITE if self.hit_flash > 0 else self.color
        pygame.draw.ellipse(surface, (4, 6, 9),
                            (x-r-5, y+r-2, 2*r+10, max(6, r//2)))
        # Подсветка ядра — цвет зависит от типа дрона.
        core_color = (255, 80, 55) if self.kind == "kamikaze" else (90, 205, 225)
        if self.kind in ("scout", "kamikaze", "shield", "robot", "heavy", "lancer"):
            glow_radius = r + 4 + int((math.sin(self.anim_time * 4) + 1) * 1.5)
            pygame.draw.circle(surface, tuple(int(c * 0.45) for c in core_color),
                               (x, y), glow_radius, 1)

        # Читаемые предупреждения перед дальними атаками: игрок видит направление
        # выстрела заранее и получает короткое окно для уклонения.
        if self.kind == "sniper" and 0 < self.shoot_timer < 0.38:
            ax, ay = self.aim_dir
            start = (int(self.x + ax * (r + 3)), int(self.y + ay * (r + 3)))
            end = (int(self.x + ax * 360), int(self.y + ay * 360))
            pygame.draw.line(surface, (80, 180, 255), start, end, 2)
            pygame.draw.circle(surface, (150, 220, 255), end, 4, 1)

        # Стрелок предупреждает о одиночном выстреле красной линией.
        if self.kind == "gunner" and 0 < self.shoot_timer < 0.24:
            ax, ay = self.aim_dir
            start = (int(self.x + ax * (r + 4)), int(self.y + ay * (r + 4)))
            end = (int(self.x + ax * 300), int(self.y + ay * 300))
            pygame.draw.line(surface, (255, 95, 75), start, end, 2)
            pygame.draw.circle(surface, (255, 170, 105), end, 4, 1)

        # Лансер фиксирует цель: розовый луч и метка дают время увернуться от залпа.
        if self.kind == "lancer" and self.lance_windup > 0:
            tx, ty = int(self.lance_target_x), int(self.lance_target_y)
            warning_color = (255, 145, 245) if int(self.lance_windup * 24) % 2 else (245, 90, 220)
            pygame.draw.line(surface, warning_color, (x, y), (tx, ty), 3)
            pulse = 10 + int((0.72 - self.lance_windup) * 10)
            pygame.draw.circle(surface, warning_color, (tx, ty), pulse, 2)
            pygame.draw.circle(surface, WHITE, (tx, ty), 4, 1)

        # Боевой робот показывает три направления будущей очереди.
        if self.kind == "robot" and 0 < self.shoot_timer < 0.28:
            ax, ay = self.aim_dir
            base_angle = math.atan2(ay, ax)
            for spread in (-0.12, 0.0, 0.12):
                angle = base_angle + spread
                start = (int(self.x + math.cos(angle) * (r + 5)),
                         int(self.y + math.sin(angle) * (r + 5)))
                end = (int(self.x + math.cos(angle) * 260),
                       int(self.y + math.sin(angle) * 260))
                pygame.draw.line(surface, (255, 115, 80), start, end, 1 if spread else 2)

        if self.kind == "heavy":
            # Оранжевые кольца предупреждают о готовящемся рывке.
            if self.heavy_windup > 0:
                pulse = 2 + int((0.58 - self.heavy_windup) * 16) % 5
                pygame.draw.circle(surface, (255, 155, 55), (x, y), r + 10 + pulse, 3)
                pygame.draw.circle(surface, (255, 215, 105), (x, y), r + 17 + pulse, 1)
            elif self.heavy_burst > 0:
                pygame.draw.circle(surface, (255, 95, 40), (x, y), r + 12, 3)

        if self.kind == "scout":
            # Маленький быстрый разведчик с четырьмя лопастями.
            pygame.draw.circle(surface, BLACK, (x, y), r + 3)
            rotor = self.anim_time * 8.0
            for i in range(4):
                angle = rotor + i * math.pi / 2
                ex = int(x + math.cos(angle) * (r + 5))
                ey = int(y + math.sin(angle) * (r + 5))
                pygame.draw.line(surface, BLACK, (x, y), (ex, ey), 6)
                pygame.draw.line(surface, color, (x, y), (ex, ey), 3)
                pygame.draw.circle(surface, LIGHT, (ex, ey), 3)
            pygame.draw.circle(surface, color, (x, y), r - 3)
            pygame.draw.circle(surface, BLACK, (x, y), r - 3, 2)
            pygame.draw.circle(surface, (255, 235, 130), (x, y), 4)

        elif self.kind == "kamikaze":
            # Мигающий предупреждающий контур перед быстрым рывком.
            if self.charge_windup > 0:
                pulse = 2 + int((0.48 - self.charge_windup) * 18) % 4
                pygame.draw.circle(surface, (255, 90, 55), (x, y), r + 10 + pulse, 2)
                pygame.draw.circle(surface, (255, 190, 80), (x, y), r + 15 + pulse, 1)
            elif self.charge_burst > 0:
                pygame.draw.circle(surface, (255, 55, 35), (x, y), r + 12, 3)
            # Красный корпус со светящимся зарядом.
            points = [(x, y-r-4), (x+r, y), (x, y+r+4), (x-r, y)]
            pygame.draw.polygon(surface, BLACK, [(px, py) for px, py in points])
            inner = [(x, y-r), (x+r-4, y), (x, y+r), (x-r+4, y)]
            pygame.draw.polygon(surface, color, inner)
            pygame.draw.circle(surface, YELLOW if self.hit_flash <= 0 else WHITE,
                               (x, y), max(3, r//4))
            pygame.draw.circle(surface, BLACK, (x, y), max(3, r//4), 2)

        elif self.kind == "gunner":
            # Дистанционный дрон с боковыми стабилизаторами и пушкой.
            body = pygame.Rect(x-r+3, y-r+5, 2*r-6, 2*r-10)
            pygame.draw.rect(surface, BLACK, body.inflate(6, 6), border_radius=5)
            pygame.draw.rect(surface, color, body, border_radius=4)
            pygame.draw.rect(surface, LIGHT, body, 2, border_radius=4)
            pygame.draw.rect(surface, BLACK, (x-4, y-5, r+13, 10))
            pygame.draw.rect(surface, LIGHT, (x+3, y-2, r+7, 4))
            pygame.draw.circle(surface, YELLOW, (x-3, y), 4)
            pygame.draw.line(surface, BLACK, (x-r-6, y-7), (x-r+1, y+7), 4)
            pygame.draw.line(surface, BLACK, (x+r-1, y-7), (x+r+6, y+7), 4)

        elif self.kind == "robot":
            # Боевой робот с квадратным бронированным корпусом.
            rect = pygame.Rect(x-22, y-22, 44, 44)
            pygame.draw.rect(surface, BLACK, rect.inflate(6, 6), border_radius=4)
            pygame.draw.rect(surface, color, rect, border_radius=4)
            pygame.draw.rect(surface, LIGHT, rect, 2, border_radius=4)
            pygame.draw.rect(surface, BLACK, (x-12, y-10, 24, 20))
            pygame.draw.rect(surface, RED if self.hit_flash <= 0 else WHITE,
                             (x-8, y-5, 16, 6))
            pygame.draw.line(surface, BLACK, (x+12, y+2), (x+30, y+2), 7)
            pygame.draw.line(surface, LIGHT, (x+17, y+2), (x+29, y+2), 2)
            pygame.draw.rect(surface, BLACK, (x-19, y+17, 12, 7))
            pygame.draw.rect(surface, BLACK, (x+7, y+17, 12, 7))

        elif self.kind == "sniper":
            # Узкий корпус, длинная винтовка и синяя оптика.
            pygame.draw.polygon(surface, BLACK,
                [(x, y-r-3), (x+r-2, y-5), (x+r-2, y+8), (x, y+r+3), (x-r+2, y+8), (x-r+2, y-5)])
            pygame.draw.polygon(surface, color,
                [(x, y-r), (x+r-5, y-4), (x+r-5, y+6), (x, y+r), (x-r+5, y+6), (x-r+5, y-4)])
            pygame.draw.circle(surface, (145, 225, 255), (x, y-3), 5)
            pygame.draw.circle(surface, BLACK, (x, y-3), 5, 2)
            pygame.draw.line(surface, BLACK, (x+3, y+7), (x+29, y+7), 5)
            pygame.draw.line(surface, WHITE, (x+7, y+7), (x+27, y+7), 2)

        elif self.kind == "lancer":
            # Узкий ромбовидный корпус с энергетическим излучателем.
            angle = self.lance_angle
            nose = (int(x + math.cos(angle) * (r + 5)),
                    int(y + math.sin(angle) * (r + 5)))
            back = (int(x - math.cos(angle) * (r - 3)),
                    int(y - math.sin(angle) * (r - 3)))
            side_x, side_y = -math.sin(angle) * (r - 5), math.cos(angle) * (r - 5)
            points = [nose, (int(x + side_x), int(y + side_y)), back,
                      (int(x - side_x), int(y - side_y))]
            pygame.draw.polygon(surface, BLACK, points)
            inner_points = [(int(x + (px - x) * 0.82), int(y + (py - y) * 0.82))
                            for px, py in points]
            pygame.draw.polygon(surface, color, inner_points)
            pygame.draw.line(surface, BLACK, (x, y), nose, 8)
            pygame.draw.line(surface, (255, 190, 250), (x, y), nose, 3)
            pygame.draw.circle(surface, WHITE, (x, y), 5)
            pygame.draw.circle(surface, (255, 190, 250), (x, y), r + 3, 1)

        elif self.kind == "shield":
            # Шестиугольный корпус и отдельный защитный контур:
            pts = [(x-r, y-7), (x-r//2, y-r), (x+r//2, y-r),
                   (x+r, y-7), (x+r, y+7), (x+r//2, y+r),
                   (x-r//2, y+r), (x-r, y+7)]
            pygame.draw.polygon(surface, BLACK, pts)
            pts2 = [(x-r+4, y-6), (x-r//2, y-r+4), (x+r//2, y-r+4),
                    (x+r-4, y-6), (x+r-4, y+6), (x+r//2, y+r-4),
                    (x-r//2, y+r-4), (x-r+4, y+6)]
            pygame.draw.polygon(surface, color, pts2)
            pygame.draw.rect(surface, BLACK, (x-5, y-9, 10, 18))
            pygame.draw.rect(surface, WHITE, (x-2, y-6, 4, 12))
            if self.shield_active:
                shield_pulse = int((math.sin(self.anim_time * 5) + 1) * 2)
                pygame.draw.circle(surface, (125, 255, 215), (x, y), r+7+shield_pulse, 3)
            else:
                pygame.draw.circle(surface, WHITE, (x, y), r+4, 1)

        elif self.kind == "heavy":
            # Крупная тяжёлая машина с бронепластинами.
            rect = pygame.Rect(x-r+2, y-r+2, 2*r-4, 2*r-4)
            pygame.draw.rect(surface, BLACK, rect.inflate(6, 6), border_radius=3)
            pygame.draw.rect(surface, color, rect, border_radius=3)
            pygame.draw.rect(surface, LIGHT, rect, 3, border_radius=3)
            pygame.draw.rect(surface, BLACK, (x-13, y-13, 26, 26))
            pygame.draw.rect(surface, (100, 72, 43), (x-9, y-9, 18, 18))
            pygame.draw.circle(surface, YELLOW, (x, y), 5)
            for ox, oy in [(-r+5, -r+5), (r-5, -r+5), (-r+5, r-5), (r-5, r-5)]:
                pygame.draw.rect(surface, BLACK, (x+ox-3, y+oy-3, 6, 6))

        # Короткая расходящаяся вспышка при попадании делает урон заметнее.
        if self.hit_pulse > 0:
            progress = 1.0 - self.hit_pulse / 0.18
            ring_radius = r + 5 + int(progress * 17)
            ring_alpha_color = (255, 225, 150) if self.hit_flash > 0 else (255, 130, 65)
            pygame.draw.circle(surface, ring_alpha_color, (x, y), ring_radius, 2)
            pygame.draw.circle(surface, WHITE, (x, y), max(2, r - int(progress * 5)), 1)

        # Полоска здоровья появляется только после первого полученного урона,
        # чтобы не загромождать комнату индикаторами над всеми целыми врагами.
        if self.hp < self.max_hp:
            width = max(34, min(58, r * 2))
            bar_height = 5
            hp_ratio = max(0.0, min(1.0, self.hp / self.max_hp))
            hp_width = int(width * hp_ratio)
            bar_x = x - width // 2
            bar_y = y - r - 13
            pygame.draw.rect(surface, BLACK, (bar_x - 1, bar_y - 1, width + 2, bar_height + 2))
            bar_color = GREEN if hp_ratio > 0.5 else ORANGE if hp_ratio > 0.25 else RED
            if hp_width > 0:
                pygame.draw.rect(surface, bar_color, (bar_x, bar_y, hp_width, bar_height))



class Trap:
    def __init__(self, x, y):
        self.x=x; self.y=y; self.r=27; self.t=random.random()*6; self.cool=0
    def update(self, player, dt):
        self.t += dt*3.5; self.cool=max(0,self.cool-dt)
        active=math.sin(self.t)>.45
        if active and self.cool<=0 and dist(self.x,self.y,player.x,player.y)<self.r:
            self.cool=1.0
            return 12
        return 0
    def draw(self,surface):
        active=math.sin(self.t)>.45
        color=RED if active else DARK_RED
        pygame.draw.circle(surface,color,(int(self.x),int(self.y)),self.r)
        pygame.draw.circle(surface,ORANGE,(int(self.x),int(self.y)),self.r,3)
        pygame.draw.line(surface,BLACK,(int(self.x-12),int(self.y-12)),(int(self.x+12),int(self.y+12)),3)
        pygame.draw.line(surface,BLACK,(int(self.x+12),int(self.y-12)),(int(self.x-12),int(self.y+12)),3)

class SupplyCrate:
    def __init__(self,x,y):
        self.x=x; self.y=y; self.opened=False
    def draw(self,surface):
        color=(65,70,78) if self.opened else (145,102,42)
        rect=pygame.Rect(int(self.x-18),int(self.y-15),36,30)
        pygame.draw.rect(surface,color,rect,border_radius=4)
        pygame.draw.rect(surface,WHITE,rect,2,border_radius=4)
        if not self.opened:
            pygame.draw.line(surface,YELLOW,(int(self.x-10),int(self.y)),(int(self.x+10),int(self.y)),3)

# ============================================================
# WEAPONS
# ============================================================

WEAPONS = [
    {"name": "ПИСТОЛЕТ", "delay": .23, "speed": 760, "damage": 1.0, "pellets": 1, "spread": .00, "color": ORANGE, "radius": 4},
    {"name": "ДРОБОВИК", "delay": .62, "speed": 680, "damage": .72, "pellets": 5, "spread": .42, "color": YELLOW, "radius": 5},
    {"name": "ИМПУЛЬСНАЯ ВИНТОВКА", "delay": .10, "speed": 820, "damage": .58, "pellets": 1, "spread": .07, "color": CYAN, "radius": 3},
    {"name": "РАКЕТНИЦА", "delay": .78, "speed": 500, "damage": 3.0, "pellets": 1, "spread": .012, "color": ORANGE, "radius": 7, "explosive_radius": 88},
]


# ============================================================
# PLAYER
# ============================================================

class Player:
    def __init__(self):
        self.x = ROOM_X + ROOM_W/2
        self.y = ROOM_Y + ROOM_H/2
        self.radius = 17

        self.max_hp = 100
        self.hp = 100

        self.damage = 2
        self.speed = 245
        self.fire_delay = .23
        self.fire_timer = 0

        self.scrap = 0
        self.kills = 0

        self.multishot = 1
        self.armor = 0
        self.crit_chance = .05
        # Elemental weapon modules are permanent once chosen from a boss reward.
        self.electric_rounds = False
        self.incendiary_rounds = False
        self.piercing_rounds = False

        self.dash_cooldown = 1.2
        self.dash_timer = 0
        self.invulnerable = 0

        # Новые боевые способности: граната и временный энергетический щит.
        self.grenade_cooldown = 5.0
        self.grenade_timer = 0
        self.shield_cooldown = 12.0
        self.shield_timer = 0
        self.shield_duration = 2.5
        self.shield_cooldown_timer = 0
        self.shield_ready = True

        self.last_shot_dir = (1, 0)
        self.muzzle_flash_timer = 0.0
        self.weapon_index = 0
        # Фаза простой пиксельной анимации ног.
        self.walk_phase = 0.0
        self.is_moving = False

    def reset_position(self):
        self.x = ROOM_X + ROOM_W/2
        self.y = ROOM_Y + ROOM_H/2

    def update(self, keys, dt):
        dx = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
        dy = int(keys[pygame.K_s]) - int(keys[pygame.K_w])

        self.is_moving = bool(dx or dy)
        if self.is_moving:
            length = math.hypot(dx, dy)
            self.x += dx/length * self.speed * dt
            self.y += dy/length * self.speed * dt
            self.walk_phase += dt * 12.0
        else:
            # Ноги плавно возвращаются в нейтральную позу, когда солдат стоит.
            self.walk_phase *= max(0.0, 1.0 - dt * 8.0)

        self.x = clamp(self.x,
                       ROOM_X + WALL_SIZE + self.radius,
                       ROOM_X + ROOM_W - WALL_SIZE - self.radius)
        self.y = clamp(self.y,
                       ROOM_Y + WALL_SIZE + self.radius,
                       ROOM_Y + ROOM_H - WALL_SIZE - self.radius)

        self.fire_timer = max(0, self.fire_timer - dt)
        self.muzzle_flash_timer = max(0.0, self.muzzle_flash_timer - dt)
        self.dash_timer = max(0, self.dash_timer - dt)
        self.grenade_timer = max(0, self.grenade_timer - dt)
        self.shield_timer = max(0, self.shield_timer - dt)
        if not self.shield_ready:
            self.shield_cooldown_timer = max(0, self.shield_cooldown_timer - dt)
            if self.shield_cooldown_timer <= 0:
                self.shield_ready = True
        self.invulnerable = max(0, self.invulnerable - dt)

    def dash(self, dx, dy):
        if self.dash_timer > 0:
            return

        length = math.hypot(dx, dy)
        if length == 0:
            return

        dx /= length
        dy /= length

        old_x, old_y = self.x, self.y
        self.x += dx * 150
        self.y += dy * 150

        self.x = clamp(self.x,
                       ROOM_X + WALL_SIZE + self.radius,
                       ROOM_X + ROOM_W - WALL_SIZE - self.radius)
        self.y = clamp(self.y,
                       ROOM_Y + WALL_SIZE + self.radius,
                       ROOM_Y + ROOM_H - WALL_SIZE - self.radius)

        self.dash_timer = self.dash_cooldown
        self.invulnerable = .22

    def shoot(self, dx, dy, bullets):
        weapon = WEAPONS[self.weapon_index]
        delay = max(.045, self.fire_delay * (weapon["delay"] / .23))
        if self.fire_timer > 0:
            return
        if dx == 0 and dy == 0:
            return

        length = math.hypot(dx, dy)
        dx /= length
        dy /= length
        self.last_shot_dir = (dx, dy)
        self.muzzle_flash_timer = 0.075
        angle = math.atan2(dy, dx)

        count = self.multishot
        pellets = weapon["pellets"]
        total = count * pellets

        for i in range(count):
            multi_offset = (i - (count-1)/2) * .13
            for p in range(pellets):
                pellet_offset = 0
                if pellets > 1:
                    pellet_offset = -weapon["spread"]/2 + weapon["spread"] * p/(pellets-1)
                # Маленькая случайность делает дробовик живее, но не ломает управление.
                jitter = random.uniform(-.025, .025) if pellets > 1 else random.uniform(-weapon["spread"], weapon["spread"])
                a = angle + multi_offset + pellet_offset + jitter
                damage = max(1, self.damage * weapon["damage"])
                if random.random() < self.crit_chance:
                    damage *= 2
                element = "normal"
                bullet_color = weapon["color"]
                if self.electric_rounds:
                    element, bullet_color = "electric", CYAN
                elif self.incendiary_rounds:
                    element, bullet_color = "fire", ORANGE
                elif self.piercing_rounds:
                    element, bullet_color = "piercing", PURPLE
                # Сочетание пробойника с мультивыстрелом даёт больше пробитий.
                extra_pierce = min(2, max(0, self.multishot - 1)) if self.piercing_rounds else 0
                bullets.append(
                    Bullet(self.x, self.y, math.cos(a), math.sin(a),
                           damage, False, weapon["speed"], bullet_color, weapon["radius"],
                           element=element, pierce=(2 + extra_pierce) if self.piercing_rounds else 0,
                           explosive_radius=weapon.get("explosive_radius", 0))
                )

        self.fire_timer = delay

    def take_damage(self, amount):
        if self.invulnerable > 0:
            return False

        amount = max(1, int(amount - self.armor))
        self.hp -= amount
        self.invulnerable = .25
        return True

    def heal(self, amount):
        self.hp = min(self.max_hp, self.hp + amount)

    def draw(self, surface):
        if self.invulnerable > 0 and int(self.invulnerable*30) % 2 == 0:
            return

        # Многослойный 16-bit спрайт бойца: тень, броня, рюкзак, визор и оружие.
        x, y = int(self.x), int(self.y)
        step = int(round(math.sin(self.walk_phase) * 3)) if self.is_moving else 0
        # Тень помогает отделить бойца от пола.
        pygame.draw.ellipse(surface, (5, 7, 10), (x-17, y+7, 34, 16))
        # Ботинки и голени с контрастными пикселями.
        pygame.draw.rect(surface, (17, 23, 24), (x-13-step, y+4, 9, 12))
        pygame.draw.rect(surface, (17, 23, 24), (x+4+step, y+4, 9, 12))
        pygame.draw.rect(surface, (104, 111, 98), (x-14-step, y+13, 10, 3))
        pygame.draw.rect(surface, (104, 111, 98), (x+4+step, y+13, 10, 3))
        # Рюкзак и корпус брони.
        pygame.draw.rect(surface, (7, 10, 13), (x-14, y-11, 28, 26))
        pygame.draw.rect(surface, (39, 57, 46), (x-13, y-8, 26, 20))
        pygame.draw.rect(surface, (57, 91, 63), (x-9, y-12, 18, 23))
        pygame.draw.rect(surface, (29, 43, 37), (x-16, y-7, 6, 15))
        pygame.draw.rect(surface, (29, 43, 37), (x+10, y-7, 6, 15))
        pygame.draw.rect(surface, (107, 132, 82), (x-7, y-10, 14, 4))
        pygame.draw.rect(surface, (24, 34, 31), (x-5, y-2, 10, 8))
        pygame.draw.rect(surface, (179, 166, 117), (x-3, y, 6, 4))
        # Шлем и голубой визор.
        pygame.draw.rect(surface, (8, 11, 14), (x-10, y-19, 20, 13))
        pygame.draw.rect(surface, (74, 91, 77), (x-8, y-18, 16, 10))
        pygame.draw.rect(surface, (83, 194, 205), (x-6, y-15, 12, 4))
        pygame.draw.rect(surface, (180, 245, 235), (x-5, y-15, 4, 2))
        pygame.draw.rect(surface, (145, 155, 148), (x-10, y-19, 20, 13), 1)
        # Наплечники и подсумки.
        pygame.draw.rect(surface, (106, 124, 84), (x-15, y-7, 6, 7))
        pygame.draw.rect(surface, (106, 124, 84), (x+9, y-7, 6, 7))
        pygame.draw.rect(surface, (180, 135, 54), (x+6, y+3, 5, 5))
        # Короткий ствол направлен в сторону последнего выстрела.
        dx, dy = self.last_shot_dir
        if abs(dx) >= abs(dy):
            if dx >= 0:
                gun = pygame.Rect(x+8, y-3, 21, 6)
                barrel = pygame.Rect(x+18, y-2, 13, 2)
            else:
                gun = pygame.Rect(x-29, y-3, 21, 6)
                barrel = pygame.Rect(x-31, y-2, 13, 2)
        elif dy >= 0:
            gun = pygame.Rect(x-3, y+8, 6, 21)
            barrel = pygame.Rect(x-2, y+18, 2, 13)
        else:
            gun = pygame.Rect(x-3, y-29, 6, 21)
            barrel = pygame.Rect(x-2, y-31, 2, 13)
        pygame.draw.rect(surface, (8, 11, 14), gun)
        pygame.draw.rect(surface, (133, 148, 151), gun, 1)
        pygame.draw.rect(surface, (201, 211, 194), barrel)

        # Короткая вспышка у дула: несколько пиксельных слоёв вместо сплошного круга.
        if self.muzzle_flash_timer > 0:
            dx, dy = self.last_shot_dir
            flash_x = int(x + dx * 34)
            flash_y = int(y + dy * 34)
            strength = self.muzzle_flash_timer / 0.075
            glow = pygame.Surface((46, 46), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 130, 35, int(55 * strength)), (23, 23), 22)
            pygame.draw.circle(glow, (255, 190, 70, int(100 * strength)), (23, 23), 12)
            surface.blit(glow, (flash_x - 23, flash_y - 23))
            pygame.draw.polygon(surface, (255, 225, 145), [
                (flash_x + int(dx * 10), flash_y + int(dy * 10)),
                (flash_x - int(dy * 4), flash_y + int(dx * 4)),
                (flash_x - int(dx * 7), flash_y - int(dy * 7)),
                (flash_x + int(dy * 4), flash_y - int(dx * 4)),
            ])


# ============================================================
# MINI BOSS
# ============================================================

class MiniBoss:
    """Мини-босс с тремя фазами, разными архетипами и предупреждаемыми атаками."""
    def __init__(self, level):
        self.level = max(1, min(10, int(level)))
        self.x = ROOM_X + ROOM_W/2
        self.y = ROOM_Y + 170
        self.radius = 48
        # Архетип определяется уровнем, поэтому корректно восстанавливается из сохранения.
        # На уровнях 4 и 8 появляется новый архетип — Охотник.
        # Остальная последовательность старых боссов сохраняется.
        self.archetype = 3 if self.level in (4, 8) else (self.level - 1) % 3
        self.archetype_names = ("РОЙ", "АРТИЛЛЕРИСТ", "ПРЕСЛЕДОВАТЕЛЬ", "ОХОТНИК")
        self.archetype_colors = ((70, 210, 150), (80, 175, 255),
                                 (255, 105, 75), (235, 75, 190))

        # Мини-босс должен ощущаться отдельным испытанием, а не обычным мобом с большим спрайтом.
        self.max_hp = 145 + self.level * 32
        self.hp = self.max_hp

        self.shoot_timer = 1.15
        self.spawn_timer = 4.0
        self.phase = 0.0
        self.combat_phase = 1
        self.warning_timer = 0.0
        self.warning_kind = "spread"
        self.shot_target = (0.0, 0.0)
        # Anti-camping: if the player stays in one spot too long, the boss
        # telegraphs a slow three-shot salvo at the last known position.
        self.player_still_timer = 0.0
        self.anti_camp_cooldown = 2.0
        self.anti_camp_warning = 0.0
        self.anti_camp_target = (self.x, self.y)
        # Артиллерист в фазах 2–3 отмечает позицию игрока и выпускает из неё радиальный залп.
        self.strike_timer = random.uniform(4.0, 5.5)
        self.strike_warning = 0.0
        self.strike_target = (self.x, self.y)

        # Способности архетипа «Охотник»: мины, рывок и ложные голограммы.
        # Все поля существуют и у старых архетипов, чтобы загрузка сохранений оставалась совместимой.
        self.hunter_mines = []
        self.hunter_mine_timer = 2.8
        self.hunter_charge_timer = 3.3
        self.hunter_charge_warning = 0.0
        self.hunter_charge_target = (self.x, self.y)
        self.hunter_charge_dir = (1.0, 0.0)
        self.hunter_charge_active = 0.0
        self.hunter_decoys = []
        self.hunter_decoy_timer = 4.8
        self.contact_cooldown = 0.0
        self.dead = False

    def update(self, player, bullets, enemies, dt):
        if self.dead:
            return

        self.phase += dt
        if getattr(player, "is_moving", False):
            self.player_still_timer = 0.0
        else:
            self.player_still_timer += dt
        self.anti_camp_cooldown = max(0.0, self.anti_camp_cooldown - dt)
        previous_anti_camp_warning = self.anti_camp_warning
        self.anti_camp_warning = max(0.0, self.anti_camp_warning - dt)
        if (self.player_still_timer >= 2.3 and self.anti_camp_cooldown <= 0
                and self.anti_camp_warning <= 0):
            self.anti_camp_target = (player.x, player.y)
            self.anti_camp_warning = 0.72
            self.anti_camp_cooldown = 5.0
            self.player_still_timer = 0.0
        if previous_anti_camp_warning > 0 and self.anti_camp_warning <= 0:
            tx, ty = self.anti_camp_target
            target_angle = math.atan2(ty - self.y, tx - self.x)
            # Three projectiles travel toward the warned-about position, not a
            # homing target, so a timely dodge remains effective.
            for offset in (-0.16, 0.0, 0.16):
                angle = target_angle + offset
                bullets.append(Bullet(self.x, self.y, math.cos(angle), math.sin(angle),
                                      9 + self.level, True, 335, YELLOW, 6))
        ratio = self.hp / max(1, self.max_hp)
        new_combat_phase = 3 if ratio <= 0.30 else 2 if ratio <= 0.65 else 1
        if new_combat_phase != self.combat_phase:
            self.combat_phase = new_combat_phase
            self.warning_timer = 0.65
            self.shoot_timer = min(self.shoot_timer, 0.45)

        # Особая атака артиллериста: босс помечает место, где стоял игрок,
        # затем выпускает из точки несколько радиальных снарядов.
        if self.archetype == 1 and self.combat_phase >= 2:
            previous_strike_warning = self.strike_warning
            self.strike_warning = max(0.0, self.strike_warning - dt)
            self.strike_timer = max(0.0, self.strike_timer - dt)
            if previous_strike_warning > 0 and self.strike_warning <= 0:
                tx, ty = self.strike_target
                count = 8 if self.combat_phase == 2 else 12
                for i in range(count):
                    a = math.tau * i / count + self.phase * 0.12
                    bullets.append(Bullet(
                        tx, ty, math.cos(a), math.sin(a),
                        8 + self.level, True, 285 + self.combat_phase * 15,
                        (255, 135, 65), 5
                    ))
            if self.strike_timer <= 0 and self.strike_warning <= 0:
                self.strike_target = (float(player.x), float(player.y))
                self.strike_warning = 0.82
                self.strike_timer = max(4.2, 5.6 - self.level * 0.08)

        # Особые атаки «Охотника»: мины с предупреждением, заряженный рывок
        # и голограммы, которые могут поглотить снаряд игрока.
        if self.archetype == 3:
            self.contact_cooldown = max(0.0, self.contact_cooldown - dt)

            previous_hunt_warning = self.hunter_charge_warning
            self.hunter_charge_warning = max(0.0, self.hunter_charge_warning - dt)
            self.hunter_charge_timer = max(0.0, self.hunter_charge_timer - dt)
            self.hunter_charge_active = max(0.0, self.hunter_charge_active - dt)

            if previous_hunt_warning > 0 and self.hunter_charge_warning <= 0:
                tx, ty = self.hunter_charge_target
                hx, hy = tx - self.x, ty - self.y
                length = math.hypot(hx, hy) or 1.0
                self.hunter_charge_dir = (hx / length, hy / length)
                self.hunter_charge_active = 0.34
                # После броска вперёд — веер снарядов по зафиксированному направлению.
                base_angle = math.atan2(hy, hx)
                offsets = (-0.24, -0.12, 0.0, 0.12, 0.24)
                for offset in offsets:
                    a = base_angle + offset
                    muzzle_x = self.x + math.cos(a) * (self.radius + 10)
                    muzzle_y = self.y + math.sin(a) * (self.radius + 10)
                    bullets.append(Bullet(
                        muzzle_x, muzzle_y, math.cos(a), math.sin(a),
                        8 + self.level, True, 390 + self.combat_phase * 25,
                        (245, 75, 185), 6
                    ))

            if (self.hunter_charge_timer <= 0 and self.hunter_charge_warning <= 0
                    and self.hunter_charge_active <= 0):
                self.hunter_charge_target = (float(player.x), float(player.y))
                self.hunter_charge_warning = 0.78
                self.hunter_charge_timer = max(3.4, 5.3 - self.combat_phase * 0.55)

            # Мины возникают рядом с текущей позицией игрока, но не прямо под ним.
            # При истечении предупреждения мина выпускает радиальный залп.
            kept_mines = []
            for mine in self.hunter_mines:
                if mine["detonated"]:
                    mine["life"] -= dt
                    if mine["life"] > 0:
                        kept_mines.append(mine)
                    continue
                previous_mine_warning = mine["warning"]
                mine["warning"] = max(0.0, mine["warning"] - dt)
                if previous_mine_warning > 0 and mine["warning"] <= 0:
                    count = 10 if self.combat_phase < 3 else 14
                    for i in range(count):
                        angle = math.tau * i / count + self.phase * 0.17
                        muzzle_x = mine["x"] + math.cos(angle) * 28
                        muzzle_y = mine["y"] + math.sin(angle) * 28
                        bullets.append(Bullet(
                            muzzle_x, muzzle_y, math.cos(angle), math.sin(angle),
                            7 + self.level, True, 285 + self.combat_phase * 20,
                            (255, 125, 65), 5
                        ))
                    mine["detonated"] = True
                    mine["life"] = 0.16
                    kept_mines.append(mine)
                else:
                    kept_mines.append(mine)
            self.hunter_mines = kept_mines

            self.hunter_mine_timer = max(0.0, self.hunter_mine_timer - dt)
            active_mines = sum(1 for mine in self.hunter_mines if not mine["detonated"])
            if self.hunter_mine_timer <= 0 and active_mines < 2:
                tx = max(ROOM_X + WALL_SIZE + 38,
                         min(ROOM_X + ROOM_W - WALL_SIZE - 38,
                             player.x + random.uniform(-58, 58)))
                ty = max(ROOM_Y + WALL_SIZE + 38,
                         min(ROOM_Y + ROOM_H - WALL_SIZE - 38,
                             player.y + random.uniform(-58, 58)))
                self.hunter_mines.append({
                    "x": tx, "y": ty, "warning": 0.98,
                    "life": 1.15, "detonated": False
                })
                self.hunter_mine_timer = max(3.3, 5.6 - self.combat_phase * 0.58)

            for decoy in self.hunter_decoys:
                decoy["life"] -= dt
            self.hunter_decoys = [d for d in self.hunter_decoys if d["life"] > 0]
            self.hunter_decoy_timer = max(0.0, self.hunter_decoy_timer - dt)
            if self.combat_phase >= 2 and self.hunter_decoy_timer <= 0:
                # Две копии возникают с боков Охотника и держатся недолго.
                for offset in (-1, 1):
                    if len(self.hunter_decoys) >= 2:
                        break
                    self.hunter_decoys.append({
                        "x": max(ROOM_X + 55, min(ROOM_X + ROOM_W - 55,
                                                  self.x + offset * random.randint(75, 115))),
                        "y": max(ROOM_Y + 70, min(ROOM_Y + ROOM_H - 75,
                                                  self.y + random.randint(-70, 70))),
                        "life": 3.5
                    })
                self.hunter_decoy_timer = 6.2 if self.combat_phase == 2 else 5.0

        # В поздних фазах босс двигается быстрее, но остаётся внутри арены.
        move_factor = 1.0 + (self.combat_phase - 1) * 0.28
        if self.archetype == 0:  # Рой: перемещается по широкой дуге и зовёт подкрепления.
            target_x = ROOM_X + ROOM_W/2 + math.cos(self.phase * (.95 + self.combat_phase * .08)) * 285
            target_y = ROOM_Y + 165 + math.sin(self.phase * 1.35) * 105
            move_speed = .95
        elif self.archetype == 1:  # Артиллерист: держится подальше от игрока.
            dxp, dyp = self.x - player.x, self.y - player.y
            d = max(1.0, math.hypot(dxp, dyp))
            target_x = player.x + dxp / d * 300 + math.cos(self.phase * .8) * 70
            target_y = player.y + dyp / d * 240 + math.sin(self.phase) * 55
            target_x = max(ROOM_X + 75, min(ROOM_X + ROOM_W - 75, target_x))
            target_y = max(ROOM_Y + 90, min(ROOM_Y + ROOM_H - 100, target_y))
            move_speed = .65
        elif self.archetype == 2:  # Преследователь: старается сблизиться с игроком.
            target_x = player.x + math.cos(self.phase * 1.8) * 95
            target_y = player.y - 65 + math.sin(self.phase * 1.5) * 75
            target_x = max(ROOM_X + 75, min(ROOM_X + ROOM_W - 75, target_x))
            target_y = max(ROOM_Y + 90, min(ROOM_Y + ROOM_H - 100, target_y))
            move_speed = 1.15
        else:  # Охотник постоянно меняет угол сближения.
            target_x = player.x + math.cos(self.phase * 2.1) * 72
            target_y = player.y + math.sin(self.phase * 1.7) * 62
            target_x = max(ROOM_X + 75, min(ROOM_X + ROOM_W - 75, target_x))
            target_y = max(ROOM_Y + 90, min(ROOM_Y + ROOM_H - 100, target_y))
            move_speed = 1.28
        follow = min(1.0, dt * move_speed * move_factor)
        self.x += (target_x - self.x) * follow
        self.y += (target_y - self.y) * follow

        # Во время рывка Охотник пересекает арену по заранее отмеченному направлению.
        if self.archetype == 3 and self.hunter_charge_active > 0:
            self.x += self.hunter_charge_dir[0] * 470 * dt
            self.y += self.hunter_charge_dir[1] * 470 * dt
            self.x = max(ROOM_X + 70, min(ROOM_X + ROOM_W - 70, self.x))
            self.y = max(ROOM_Y + 85, min(ROOM_Y + ROOM_H - 85, self.y))

        self.warning_timer = max(0.0, self.warning_timer - dt)
        self.shoot_timer -= dt
        self.spawn_timer -= dt

        if self.shoot_timer <= 0 and self.warning_timer <= 0:
            dx = player.x - self.x
            dy = player.y - self.y
            angle = math.atan2(dy, dx)
            damage = 11 + int(self.level * 1.35)

            if self.archetype == 0:
                # Рой: много снарядов по кругу, чтобы нельзя было стоять на месте.
                count = 8 if self.combat_phase == 1 else 10 if self.combat_phase == 2 else 14
                for i in range(count):
                    a = math.tau * i / count + self.phase * .22
                    bullets.append(Bullet(self.x, self.y, math.cos(a), math.sin(a),
                                          max(7, damage - 3), True, 315 + self.combat_phase * 25, GREEN, 5))
                # Дополнительный прицельный снаряд направляет игрока в движение.
                if self.combat_phase >= 2:
                    bullets.append(Bullet(self.x, self.y, math.cos(angle), math.sin(angle),
                                          damage, True, 410, ORANGE, 7))
                self.shoot_timer = max(.82, 1.35 - self.level * .025)
            elif self.archetype == 1:
                # Артиллерист: медленный, но плотный прицельный залп.
                offsets = (-.20, 0, .20) if self.combat_phase == 1 else (-.32, -.16, 0, .16, .32)
                for spread in offsets:
                    a = angle + spread
                    bullets.append(Bullet(self.x, self.y, math.cos(a), math.sin(a),
                                          damage + 2, True, 300 + self.combat_phase * 25, BLUE, 7))
                if self.combat_phase == 3:
                    # Второй залп с небольшим угловым сдвигом, а не мгновенное самонаведение.
                    for spread in (-.10, .10):
                        a = angle + spread
                        bullets.append(Bullet(self.x, self.y, math.cos(a), math.sin(a),
                                              damage, True, 360, PURPLE, 6))
                self.shoot_timer = max(1.0, 1.65 - self.level * .035 - self.combat_phase * .08)
            elif self.archetype == 2:
                # Преследователь: веер вблизи, чтобы игроку приходилось постоянно менять позицию.
                count = 5 if self.combat_phase == 1 else 7 if self.combat_phase == 2 else 9
                spread_width = .20 if self.combat_phase == 1 else .28
                for i in range(count):
                    spread = (i - (count - 1) / 2) * spread_width
                    a = angle + spread
                    bullets.append(Bullet(self.x, self.y, math.cos(a), math.sin(a),
                                          damage + (2 if self.combat_phase == 3 else 0), True,
                                          390 + self.combat_phase * 25, RED, 6))
                if self.combat_phase == 3 and self.warning_kind == "radial":
                    for i in range(10):
                        a = math.tau * i / 10 + self.phase * .3
                        bullets.append(Bullet(self.x, self.y, math.cos(a), math.sin(a),
                                              max(7, damage - 3), True, 330, PURPLE, 5))
                self.warning_kind = "radial" if self.combat_phase == 3 and self.warning_kind != "radial" else "spread"
                self.shoot_timer = max(.78, 1.2 - self.level * .02 - self.combat_phase * .06)
            else:
                # Охотник выпускает широкий, но читаемый веер ярко-розовых снарядов.
                count = 5 if self.combat_phase == 1 else 7 if self.combat_phase == 2 else 9
                spread_width = .18 if self.combat_phase == 1 else .22 if self.combat_phase == 2 else .25
                for i in range(count):
                    spread = (i - (count - 1) / 2) * spread_width
                    a = angle + spread
                    bullets.append(Bullet(
                        self.x, self.y, math.cos(a), math.sin(a),
                        damage + (3 if self.combat_phase == 3 else 0), True,
                        370 + self.combat_phase * 30, (245, 75, 185), 6
                    ))
                self.shoot_timer = max(.9, 1.35 - self.level * .02 - self.combat_phase * .08)
            # Предупреждение даёт короткое время на реакцию перед следующим залпом.
            self.warning_timer = .28 if self.combat_phase >= 2 else .18

        # Подкрепление появляется реже, чем в финальной фазе, но регулярно давит на игрока.
        max_minions = 6 if self.combat_phase == 1 else 7 if self.combat_phase == 2 else 8
        if self.spawn_timer <= 0 and len(enemies) < max_minions:
            spawn_count = 2 if self.combat_phase == 1 else 2 if self.combat_phase == 2 else 3
            if self.archetype == 0:
                pool = ["scout", "kamikaze"] if self.combat_phase < 3 else ["kamikaze", "shield"]
            elif self.archetype == 1:
                pool = ["gunner", "sniper", "lancer"] if self.combat_phase >= 3 else (["gunner", "sniper"] if self.combat_phase >= 2 else ["scout", "gunner"])
            elif self.archetype == 2:
                pool = ["kamikaze", "gunner", "shield", "lancer"] if self.combat_phase >= 2 else ["scout", "kamikaze"]
            else:
                pool = ["lancer", "kamikaze", "sniper"] if self.combat_phase < 3 else ["lancer", "heavy", "shield"]
            for _ in range(spawn_count):
                if len(enemies) >= max_minions:
                    break
                side = random.choice(["left", "right"])
                x = ROOM_X + 60 if side == "left" else ROOM_X + ROOM_W - 60
                y = random.randint(ROOM_Y + 100, ROOM_Y + ROOM_H - 80)
                enemies.append(Enemy(random.choice(pool), x, y, self.level))
            self.spawn_timer = max(2.35, 4.25 - self.combat_phase * .58 - self.level * .055)

    def draw(self, surface):
        """Детализированный пиксельный рендер мини-боссов; логика боя не меняется."""
        x, y = int(self.x), int(self.y)
        t = self.phase
        pulse = 0.5 + 0.5 * math.sin(t * 4.2)
        spin = t * (1.15 + self.combat_phase * 0.42)
        hp_ratio = max(0.0, min(1.0, self.hp / max(1, self.max_hp)))
        base = self.archetype_colors[self.archetype]
        if self.combat_phase == 2:
            base = (255, 142, 58)
        elif self.combat_phase == 3:
            base = (196, 70, 235)
        bright = tuple(min(255, int(c * (1.12 + pulse * .18))) for c in base)
        dark = tuple(max(0, int(c * .34)) for c in base)

        # Мягкая подсветка, тень и внешний энергетический контур.
        glow = pygame.Surface((210, 210), pygame.SRCALPHA)
        glow_alpha = 22 + int(18 * pulse)
        pygame.draw.circle(glow, (*base, glow_alpha), (105, 105), 82 + int(4*pulse))
        pygame.draw.circle(glow, (*base, glow_alpha), (105, 105), 65, 0)
        surface.blit(glow, (x-105, y-105))
        pygame.draw.ellipse(surface, (3, 5, 8), (x-67, y+39, 134, 27))
        pygame.draw.circle(surface, dark, (x, y), 65, 2)
        pygame.draw.circle(surface, bright, (x, y), 59 + int(2*pulse), 2)
        pygame.draw.circle(surface, (18, 22, 30), (x, y), 51)

        # Восемь механических сегментов вращаются вокруг корпуса.
        for i in range(8):
            a = spin + i * math.tau / 8
            ca, sa = math.cos(a), math.sin(a)
            inner = (int(x + ca*55), int(y + sa*55))
            outer = (int(x + ca*(77 + (4 if self.combat_phase == 3 else 0))),
                     int(y + sa*(77 + (4 if self.combat_phase == 3 else 0))))
            pygame.draw.line(surface, (7, 10, 15), inner, outer, 13)
            pygame.draw.line(surface, bright, inner, outer, 7)
            pygame.draw.circle(surface, (185, 197, 205), outer, 5)
            pygame.draw.circle(surface, (35, 42, 52), outer, 5, 2)
            pygame.draw.circle(surface, base, (int(x+ca*66), int(y+sa*66)), 3)

        # Четыре бронированных двигателя с разными формами у каждого архетипа.
        for i in range(4):
            a = spin * (1.25 if self.archetype == 3 else .72) + i * math.pi/2
            px, py = int(x + math.cos(a)*43), int(y + math.sin(a)*43)
            pod = pygame.Rect(px-13, py-10, 26, 20)
            pygame.draw.rect(surface, (5, 7, 11), pod.inflate(5, 5), border_radius=4)
            pygame.draw.rect(surface, (65, 75, 87), pod, border_radius=3)
            pygame.draw.rect(surface, bright, pod, 2, border_radius=3)
            pygame.draw.circle(surface, (255, 210, 115) if self.combat_phase < 3 else (255, 80, 110),
                               (px, py), 4 + int(pulse*2))

        # Архетипные элементы корпуса: рой, артиллерия, преследователь, охотник.
        if self.archetype == 0:  # РОЙ — четыре мини-дрона вокруг центрального гнезда.
            pygame.draw.circle(surface, (8, 13, 19), (x, y), 37)
            pygame.draw.circle(surface, base, (x, y), 33)
            for i in range(6):
                a = -spin*1.6 + i*math.tau/6
                sx, sy = int(x+math.cos(a)*24), int(y+math.sin(a)*24)
                pygame.draw.circle(surface, (8, 12, 18), (sx, sy), 9)
                pygame.draw.circle(surface, (125, 255, 190), (sx, sy), 5)
                pygame.draw.circle(surface, WHITE, (sx, sy), 2)
            pygame.draw.circle(surface, (220, 255, 235), (x, y), 8, 2)
        elif self.archetype == 1:  # АРТИЛЛЕРИСТ — тяжёлая башня и два ствола.
            pygame.draw.circle(surface, (9, 14, 22), (x, y), 39)
            pygame.draw.circle(surface, (54, 77, 99), (x, y), 34)
            pygame.draw.circle(surface, bright, (x, y), 30, 3)
            for side in (-1, 1):
                barrel = pygame.Rect(x + side*17 - 7, y-49, 14, 43)
                pygame.draw.rect(surface, (8, 11, 17), barrel.inflate(5, 5), border_radius=3)
                pygame.draw.rect(surface, (111, 135, 153), barrel, border_radius=2)
                pygame.draw.rect(surface, bright, barrel, 2, border_radius=2)
                pygame.draw.rect(surface, (255, 195, 100), (barrel.x+3, barrel.y+4, 8, 7))
            pygame.draw.circle(surface, (205, 235, 255), (x, y+5), 9)
            pygame.draw.circle(surface, (25, 42, 58), (x, y+5), 5)
        elif self.archetype == 2:  # ПРЕСЛЕДОВАТЕЛЬ — клиновидная броня и массивные челюсти.
            hull = [(x, y-48), (x+43, y-20), (x+51, y+24), (x+20, y+45),
                    (x, y+31), (x-20, y+45), (x-51, y+24), (x-43, y-20)]
            pygame.draw.polygon(surface, (5, 8, 13), [(px, py+5) for px, py in hull])
            pygame.draw.polygon(surface, (82, 43, 39), hull)
            pygame.draw.polygon(surface, bright, hull, 3)
            pygame.draw.polygon(surface, (25, 29, 37), [(x, y-29), (x+25, y-8), (x+17, y+26),
                                                        (x, y+36), (x-17, y+26), (x-25, y-8)])
            for side in (-1, 1):
                pygame.draw.line(surface, (9, 12, 17), (x+side*25, y+4), (x+side*54, y+32), 12)
                pygame.draw.line(surface, (230, 105, 74), (x+side*25, y+4), (x+side*54, y+32), 5)
            pygame.draw.circle(surface, (255, 235, 190), (x, y-3), 10)
            pygame.draw.circle(surface, (255, 75, 55), (x, y-3), 5)
        else:  # ОХОТНИК — угловатый стелс-корпус, сенсоры и энергетические крылья.
            hull = [(x, y-54), (x+35, y-17), (x+53, y+13), (x+22, y+39),
                    (x, y+28), (x-22, y+39), (x-53, y+13), (x-35, y-17)]
            pygame.draw.polygon(surface, (4, 8, 15), hull)
            pygame.draw.polygon(surface, (69, 31, 77), [(x+(px-x)*.88, y+(py-y)*.88) for px,py in hull])
            pygame.draw.polygon(surface, bright, hull, 3)
            for side in (-1, 1):
                wing = [(x+side*25, y-7), (x+side*76, y-35), (x+side*62, y+5), (x+side*28, y+19)]
                pygame.draw.polygon(surface, (10, 14, 23), wing)
                pygame.draw.polygon(surface, (235, 80, 190), wing, 2)
                pygame.draw.line(surface, (255, 170, 235), (x+side*35, y+3), (x+side*65, y-20), 3)
            pygame.draw.circle(surface, (255, 225, 250), (x, y-5), 12)
            pygame.draw.circle(surface, (255, 55, 175), (x, y-5), 7)
            pygame.draw.circle(surface, WHITE, (x, y-5), 2)

        # Тонкие панели и болты добавляют ощущение собранной из деталей машины.
        for side in (-1, 1):
            pygame.draw.line(surface, (165, 178, 188), (x+side*24, y-25), (x+side*37, y-12), 2)
            pygame.draw.circle(surface, (215, 220, 225), (x+side*31, y+25), 3)
        pygame.draw.arc(surface, (185, 195, 205), (x-43, y-43, 86, 86), .25, 2.85, 2)
        pygame.draw.arc(surface, (35, 43, 54), (x-34, y-34, 68, 68), 3.35, 5.95, 4)

        # Ядро пульсирует и меняет цвет по фазам; открытое окно уязвимости — голубое.
        core = CYAN if self.warning_timer > 0 else (WHITE if self.combat_phase == 3 and pulse > .72 else base)
        core_r = 10 + int(3*pulse)
        pygame.draw.circle(surface, (5, 8, 13), (x, y), 17)
        pygame.draw.circle(surface, core, (x, y), core_r)
        pygame.draw.circle(surface, WHITE, (x-3, y-3), 3)
        pygame.draw.circle(surface, bright, (x, y), 20 + int(3*pulse), 2)

        # Спецэффекты атак остаются читаемыми и не перекрывают модель босса.
        if self.archetype == 3:
            for mine in self.hunter_mines:
                mx, my = int(mine["x"]), int(mine["y"])
                if not mine["detonated"]:
                    mr = 19 + int(5*math.sin(pygame.time.get_ticks()*.025))
                    pygame.draw.circle(surface, (255, 105, 65), (mx, my), mr, 3)
                    pygame.draw.circle(surface, (255, 210, 105), (mx, my), 7, 2)
            for decoy in self.hunter_decoys:
                dx, dy = int(decoy["x"]), int(decoy["y"])
                pygame.draw.circle(surface, (85, 225, 255), (dx, dy), 28, 2)
                pygame.draw.polygon(surface, (85, 225, 255),
                                    [(dx,dy-22),(dx+22,dy),(dx,dy+22),(dx-22,dy)], 2)
            if self.hunter_charge_warning > 0:
                tx, ty = map(int, self.hunter_charge_target)
                warning = (255, 135, 220) if int(self.hunter_charge_warning*22)%2 else WHITE
                pygame.draw.line(surface, warning, (x,y), (tx,ty), 3)
                pygame.draw.circle(surface, warning, (tx,ty), 23, 2)
                text(surface, "РЫВОК!", SMALL, warning, tx, ty-32, True)
        if self.anti_camp_warning > 0:
            tx, ty = map(int, self.anti_camp_target)
            pygame.draw.line(surface, YELLOW, (x,y), (tx,ty), 2)
            pygame.draw.circle(surface, YELLOW, (tx,ty), 18, 2)
        if self.strike_warning > 0:
            tx, ty = map(int, self.strike_target)
            pygame.draw.circle(surface, (255, 145, 65), (tx,ty), 42, 2)
            pygame.draw.circle(surface, (255, 210, 115), (tx,ty), 12+int(8*pulse), 3)
            text(surface, "АРТУДАР!", SMALL, (255, 175, 95), tx, ty-53, True)
        if self.warning_timer > 0:
            pygame.draw.circle(surface, YELLOW, (x,y), 88+int(5*pulse), 3)

        # Полоса здоровья и подпись остаются компактными над моделью.
        width = 170
        bar_x, bar_y = x-width//2, y-103
        pygame.draw.rect(surface, (3,5,8), (bar_x-2, bar_y-2, width+4, 13), border_radius=3)
        pygame.draw.rect(surface, (65,72,82), (bar_x, bar_y, width, 9), border_radius=2)
        bar_color = GREEN if hp_ratio > .6 else ORANGE if hp_ratio > .3 else RED
        if hp_ratio > 0:
            pygame.draw.rect(surface, bar_color, (bar_x, bar_y, int(width*hp_ratio), 9), border_radius=2)
        pygame.draw.rect(surface, (190,200,210), (bar_x-2, bar_y-2, width+4, 13), 1, border_radius=3)
        label = SMALL.render(f"{self.archetype_names[self.archetype]}  /  ФАЗА {self.combat_phase}", True, WHITE)
        surface.blit(label, label.get_rect(center=(x, bar_y-13)))


# ============================================================
# GAME
# ============================================================

class FloatingDamageText:
    """Короткая подпись урона над врагом для более понятной обратной связи."""
    def __init__(self, x, y, amount, critical=False):
        self.x = float(x)
        self.y = float(y)
        self.amount = int(amount)
        self.life = 0.62
        self.max_life = self.life
        self.critical = critical

    def update(self, dt):
        self.y -= 34 * dt
        self.life -= dt

    def draw(self, surface):
        if self.life <= 0:
            return
        font = MEDIUM if self.critical else SMALL
        color = YELLOW if self.critical else WHITE
        image = font.render(str(self.amount) + ("!" if self.critical else ""), True, color)
        image.set_alpha(int(255 * min(1.0, self.life / 0.18)))
        rect = image.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(image, rect)


class FloatingPickupText:
    """Яркая подпись при получении запчастей, лечения или улучшения."""
    def __init__(self, x, y, label, color=CYAN):
        self.x = float(x)
        self.y = float(y)
        self.label = str(label)
        self.color = color
        self.life = 0.82
        self.max_life = self.life

    def update(self, dt):
        self.y -= 30 * dt
        self.life -= dt

    def draw(self, surface):
        if self.life <= 0:
            return
        # Все подписи подбора одного компактного размера, чтобы не закрывать обзор.
        font = SMALL
        alpha = int(255 * min(1.0, self.life / 0.2))
        image = font.render(self.label, True, self.color)
        image.set_alpha(alpha)
        rect = image.get_rect(center=(int(self.x), int(self.y)))
        # Тёмная обводка оставляет надпись читаемой на любом участке пола.
        outline = font.render(self.label, True, BLACK)
        outline.set_alpha(alpha)
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surface.blit(outline, rect.move(ox, oy))
        surface.blit(image, rect)


ACHIEVEMENTS = [
    ("first_run", "ПЕРВЫЙ ВЫЛЕТ", "Начать первый забег", lambda p: p["runs"] >= 1),
    ("drone_slayer", "ОХОТНИК", "Уничтожить 100 врагов суммарно", lambda p: p["total_kills"] >= 100),
    ("veteran", "ВЕТЕРАН", "Достичь 5-го уровня", lambda p: p["best_level"] >= 5),
    ("champion", "ЧЕМПИОН", "Одержать первую победу", lambda p: p["wins"] >= 1),
]


class Game:
    def __init__(self):
        self.state = "menu"
        self.paused_from = "playing"
        self.player = Player()

        self.level = 1
        self.room = 1
        self.level_room_count = random.randint(MIN_ROOMS_PER_LEVEL, MAX_ROOMS_PER_LEVEL)
        self.map_cells = []
        self.current_cell = (0, 0)
        self.boss_cell = (0, 0)
        self.visited_cells = set()
        self.cleared_cells = set()
        self.room_types = {}
        self.room_obstacles = {}
        # Снимки незачищенных комнат: враги, добыча, ловушки и ящики.
        self.room_states = {}
        self.obstacles = []

        self.enemies = []
        self.bullets = []
        self.scraps = []
        self.medkits = []
        self.particles = []
        self.shockwaves = []
        self.damage_texts = []
        self.traps = []
        self.crates = []
        self.room_type = "combat"
        self.room_type_override = None
        self.map_options = []
        self.map_selected = 0

        self.exit_open = False
        self.exit_rect = pygame.Rect(0, 0, 0, 0)
        # Отдельный портал в следующую зону появляется в комнате босса.
        self.level_exit_open = False
        self.level_exit_rect = pygame.Rect(ROOM_X + ROOM_W//2 - 46, ROOM_Y + ROOM_H - 142, 92, 78)
        self.shop_buy_button = pygame.Rect(185, 555, 280, 54)
        self.shop_leave_button = pygame.Rect(495, 555, 280, 54)
        self.upgrade_continue_button = pygame.Rect(WIDTH//2 - 170, 610, 340, 52)
        self.door_rects = {}
        self.door_open = False
        self.transition_timer = 0
        self.transition_side = None
        self.entry_side = None
        self.door_lock_timer = 0.0
        self.entry_block_side = None

        self.boss = None
        self.final_boss = None
        # Destructible cover used only in the final boss arena.
        self.boss_cover = []

        self.message = ""
        self.message_timer = 0
        # Короткая красная вспышка при получении урона.
        self.hurt_flash_timer = 0.0
        self.boss_death_fx_done = False

        self.upgrade_options = []
        self.upgrade_selected = 0
        self.boss_reward_options = []
        self.boss_reward_selected = 0
        self.shop_options = []
        self.shop_selected = 0

        self.rooms_cleared = 0
        self.best_level = 1
        self.run_recorded = False
        self.profile = self.load_profile()
        self.achievement_return_state = "menu"

    # ---------------- PILOT PROFILE ----------------

    def load_profile(self):
        """Читает постоянную статистику; повреждённый файл не мешает запуску игры."""
        defaults = {"runs": 0, "wins": 0, "total_kills": 0, "best_level": 1, "unlocked": []}
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = {key: max(default, int(data.get(key, default)))
                       for key, default in defaults.items() if key != "unlocked"}
            profile["unlocked"] = list(data.get("unlocked", [])) if isinstance(data.get("unlocked", []), list) else []
            return profile
        except (OSError, ValueError, TypeError):
            return defaults

    def record_run(self, victory=False):
        """Сохраняет итог забега ровно один раз."""
        if self.run_recorded:
            return
        self.run_recorded = True
        self.profile["runs"] += 1
        self.profile["total_kills"] += max(0, int(self.player.kills))
        self.profile["best_level"] = max(self.profile["best_level"], int(self.level))
        if victory:
            self.profile["wins"] += 1
        for achievement_id, _title, _description, condition in ACHIEVEMENTS:
            if condition(self.profile) and achievement_id not in self.profile["unlocked"]:
                self.profile["unlocked"].append(achievement_id)
        try:
            with open(PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, ensure_ascii=False, indent=2)
        except OSError:
            self.show_message("Не удалось записать статистику пилота", 3)

    # ---------------- SAVE ----------------

    def save(self):
        data = {
            "save_version": 2,
            "level": self.level,
            "room": self.room,
            "level_room_count": self.level_room_count,
            "map_cells": [list(cell) for cell in self.map_cells],
            "current_cell": list(self.current_cell),
            "boss_cell": list(self.boss_cell),
            "visited_cells": [list(cell) for cell in self.visited_cells],
            "cleared_cells": [list(cell) for cell in self.cleared_cells],
            "room_types": {f"{cell[0]},{cell[1]}": kind for cell, kind in self.room_types.items()},
            "room_obstacles": {f"{cell[0]},{cell[1]}": [list(r) for r in rects] for cell, rects in self.room_obstacles.items()},
            "room_states": self.room_states,
            "scrap": self.player.scrap,
            "hp": self.player.hp,
            "player_x": self.player.x,
            "player_y": self.player.y,
            "kills": self.player.kills,
            "max_hp": self.player.max_hp,
            "damage": self.player.damage,
            "speed": self.player.speed,
            "fire_delay": self.player.fire_delay,
            "multishot": self.player.multishot,
            "armor": self.player.armor,
            "crit_chance": self.player.crit_chance,
            "electric_rounds": self.player.electric_rounds,
            "incendiary_rounds": self.player.incendiary_rounds,
            "piercing_rounds": self.player.piercing_rounds,
            "weapon_index": self.player.weapon_index,
            "grenade_timer": self.player.grenade_timer,
            "shield_ready": self.player.shield_ready,
            "rooms_cleared": self.rooms_cleared,
            "best_level": self.best_level,
        }

        # Сначала записываем временный файл, а затем заменяем основной.
        # Если запись прервётся, старое сохранение останется целым.
        temp_file = SAVE_FILE + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, SAVE_FILE)
        except (OSError, TypeError, ValueError) as error:
            try:
                with open(CRASH_LOG, "a", encoding="utf-8") as log:
                    log.write("\nОшибка сохранения игры:\n")
                    log.write(repr(error) + "\n")
            except OSError:
                pass
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass
            self.show_message("ОШИБКА СОХРАНЕНИЯ — см. crash_log.txt", 3)

    def load_save(self):
        if not os.path.exists(SAVE_FILE):
            self.show_message("Сохранения нет", 2)
            return

        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.level = int(data.get("level", 1))
            self.room = int(data.get("room", 1))
            self.level_room_count = int(data.get("level_room_count", random.randint(MIN_ROOMS_PER_LEVEL, MAX_ROOMS_PER_LEVEL)))
            self.map_cells = [tuple(cell) for cell in data.get("map_cells", []) if isinstance(cell, list) and len(cell) == 2]
            self.current_cell = tuple(data.get("current_cell", [0, 0]))
            self.boss_cell = tuple(data.get("boss_cell", self.map_cells[-1] if self.map_cells else [0, 0]))
            self.visited_cells = {tuple(cell) for cell in data.get("visited_cells", []) if isinstance(cell, list) and len(cell) == 2}
            self.cleared_cells = {tuple(cell) for cell in data.get("cleared_cells", []) if isinstance(cell, list) and len(cell) == 2}
            self.room_types = {}
            for key, kind in data.get("room_types", {}).items():
                try:
                    x, y = [int(v) for v in key.split(",")]
                    self.room_types[(x, y)] = str(kind)
                except (ValueError, AttributeError):
                    pass
            self.room_obstacles = {}
            for key, rects in data.get("room_obstacles", {}).items():
                try:
                    x, y = [int(v) for v in key.split(",")]
                    self.room_obstacles[(x, y)] = [tuple(int(v) for v in r) for r in rects if len(r) == 4]
                except (ValueError, TypeError, AttributeError):
                    pass
            raw_room_states = data.get("room_states", {})
            self.room_states = raw_room_states if isinstance(raw_room_states, dict) else {}
            if not self.map_cells:
                self.generate_level_map()
            self.player.scrap = max(0, int(data.get("scrap", 0)))
            self.player.max_hp = max(1, int(data.get("max_hp", 100)))
            # Older save files do not contain these fields, so sensible defaults
            # keep compatibility with saves from v4.x.
            self.player.hp = int(clamp(int(data.get("hp", self.player.max_hp)), 1, self.player.max_hp))
            self.player.kills = max(0, int(data.get("kills", 0)))
            self.player.damage = max(1, int(data.get("damage", 2)))
            self.player.speed = int(data.get("speed", 245))
            self.player.fire_delay = float(data.get("fire_delay", .23))
            self.player.multishot = int(data.get("multishot", 1))
            self.player.armor = int(data.get("armor", 0))
            self.player.crit_chance = float(data.get("crit_chance", .05))
            self.player.electric_rounds = bool(data.get("electric_rounds", False))
            self.player.incendiary_rounds = bool(data.get("incendiary_rounds", False))
            self.player.piercing_rounds = bool(data.get("piercing_rounds", False))
            # A save should never activate conflicting elemental modules together.
            if self.player.electric_rounds:
                self.player.incendiary_rounds = self.player.piercing_rounds = False
            elif self.player.incendiary_rounds:
                self.player.piercing_rounds = False
            self.player.weapon_index = int(clamp(int(data.get("weapon_index", 0)), 0, len(WEAPONS)-1))
            self.player.grenade_timer = max(0.0, float(data.get("grenade_timer", 0)))
            self.player.shield_ready = bool(data.get("shield_ready", True))
            self.rooms_cleared = max(0, int(data.get("rooms_cleared", 0)))
            self.best_level = max(self.level, int(data.get("best_level", self.level)))

            self.state = "playing"
            self.load_room()
            # load_room places the player at the room entrance; restore the exact
            # saved position afterward, but clamp it to the playable room bounds.
            saved_x = float(data.get("player_x", self.player.x))
            saved_y = float(data.get("player_y", self.player.y))
            self.player.x = clamp(saved_x, ROOM_X + WALL_SIZE + self.player.radius,
                                  ROOM_X + ROOM_W - WALL_SIZE - self.player.radius)
            self.player.y = clamp(saved_y, ROOM_Y + WALL_SIZE + self.player.radius,
                                  ROOM_Y + ROOM_H - WALL_SIZE - self.player.radius)
            if self.point_blocked_by_obstacle(self.player.x, self.player.y, self.player.radius):
                self.player.reset_position()
            self.show_message("СОХРАНЕНИЕ ЗАГРУЖЕНО", 2)

        except (OSError, ValueError, json.JSONDecodeError):
            self.show_message("Ошибка загрузки сохранения", 2)

    # ---------------- START ----------------

    def start_game(self):
        self.run_recorded = False
        self.state = "playing"
        self.player = Player()
        self.level = 1
        self.room = 1
        self.rooms_cleared = 0
        self.generate_level_map()
        self.best_level = 1
        self.load_room()

    def generate_level_map(self):
        """Создаёт связную случайную карту из 6–10 комнат в духе room-based roguelike."""
        count = random.randint(MIN_ROOMS_PER_LEVEL, MAX_ROOMS_PER_LEVEL)
        cells = {(0, 0)}
        frontier = [(0, 0)]
        directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]

        while len(cells) < count:
            base = random.choice(frontier)
            random.shuffle(directions)
            added = False
            for dx, dy in directions:
                candidate = (base[0] + dx, base[1] + dy)
                if candidate in cells:
                    continue
                if abs(candidate[0]) > 4 or abs(candidate[1]) > 3:
                    continue
                cells.add(candidate)
                frontier.append(candidate)
                added = True
                break
            if not added:
                frontier = list(cells)

        cells = list(cells)
        # Босс находится в одной из самых дальних комнат — путь каждый раз разный.
        farthest = max(cells[1:], key=lambda c: (abs(c[0]) + abs(c[1]), random.random()))
        cells.remove(farthest)
        self.map_cells = [(0, 0)] + cells + [farthest]
        self.level_room_count = len(self.map_cells)
        self.current_cell = (0, 0)
        self.boss_cell = farthest
        self.room = 1
        self.visited_cells = {(0, 0)}
        self.cleared_cells = set()
        self.room_types = {(0, 0): "combat"}
        self.room_obstacles = {}
        self.obstacles = []

    def neighbors_of(self, cell):
        x, y = cell
        result = {}
        for side, delta in {
            "top": (0, -1),
            "right": (1, 0),
            "bottom": (0, 1),
            "left": (-1, 0),
        }.items():
            target = (x + delta[0], y + delta[1])
            if target in self.map_cells:
                result[side] = target
        return result

    def room_number_for(self, cell):
        try:
            return self.map_cells.index(cell) + 1
        except ValueError:
            return 1

    def _room_state_key(self, cell=None):
        cell = self.current_cell if cell is None else cell
        return f"{cell[0]},{cell[1]}"

    def capture_room_state(self):
        """Сохраняет текущую незачищенную комнату перед переходом."""
        if self.current_cell in self.cleared_cells:
            self.room_states.pop(self._room_state_key(), None)
            return
        state = {
            "enemies": [],
            "scraps": [[float(o.x), float(o.y), int(o.amount)] for o in self.scraps],
            "medkits": [[float(o.x), float(o.y)] for o in self.medkits],
            "traps": [[float(o.x), float(o.y), float(o.t), float(o.cool)] for o in self.traps],
            "crates": [[float(o.x), float(o.y), bool(o.opened)] for o in self.crates],
            "boss": None,
        }
        for e in self.enemies:
            if e.dead:
                continue
            state["enemies"].append({
                "kind": e.kind, "x": float(e.x), "y": float(e.y),
                "hp": int(e.hp), "stun": float(e.stun),
                "shoot_timer": float(e.shoot_timer),
                "ability_timer": float(e.ability_timer),
                "charge_timer": float(e.charge_timer),
                "shield_active": bool(e.shield_active),
                "orbit": int(e.orbit), "anim_time": float(e.anim_time),
            })
        if self.boss is not None and not self.boss.dead:
            state["boss"] = {
                "x": float(self.boss.x), "y": float(self.boss.y),
                "hp": int(self.boss.hp), "phase": float(self.boss.phase),
                "shoot_timer": float(self.boss.shoot_timer),
                "spawn_timer": float(self.boss.spawn_timer),
            }
        self.room_states[self._room_state_key()] = state

    def restore_room_state(self, state):
        """Восстанавливает сохранённую незачищенную комнату."""
        try:
            for item in state.get("enemies", []):
                kind = item.get("kind")
                if kind not in ENEMY_DATA:
                    continue
                e = Enemy(kind, float(item["x"]), float(item["y"]), self.level)
                e.hp = max(1, min(e.max_hp, int(item.get("hp", e.max_hp))))
                for attr in ("stun", "shoot_timer", "ability_timer", "charge_timer", "anim_time"):
                    if attr in item:
                        setattr(e, attr, float(item[attr]))
                if "shield_active" in item:
                    e.shield_active = bool(item["shield_active"])
                if "orbit" in item:
                    e.orbit = int(item["orbit"])
                self.enemies.append(e)
            self.scraps = [Scrap(float(x), float(y), int(amount)) for x, y, amount in state.get("scraps", [])]
            self.medkits = [Medkit(float(x), float(y)) for x, y in state.get("medkits", [])]
            self.traps = []
            for x, y, t, cool in state.get("traps", []):
                obj = Trap(float(x), float(y)); obj.t = float(t); obj.cool = float(cool)
                self.traps.append(obj)
            self.crates = []
            for x, y, opened in state.get("crates", []):
                obj = SupplyCrate(float(x), float(y)); obj.opened = bool(opened)
                self.crates.append(obj)
            boss_data = state.get("boss")
            if boss_data:
                self.boss = MiniBoss(self.level)
                self.boss.x = float(boss_data.get("x", self.boss.x))
                self.boss.y = float(boss_data.get("y", self.boss.y))
                self.boss.hp = max(1, min(self.boss.max_hp, int(boss_data.get("hp", self.boss.max_hp))))
                self.boss.phase = float(boss_data.get("phase", 0))
                self.boss.shoot_timer = float(boss_data.get("shoot_timer", 1))
                self.boss.spawn_timer = float(boss_data.get("spawn_timer", 4))
            return True
        except (TypeError, ValueError, KeyError):
            self.enemies.clear(); self.scraps.clear(); self.medkits.clear(); self.traps.clear(); self.crates.clear()
            self.boss = None
            return False

    def load_room(self):
        self.enemies.clear()
        self.bullets.clear()
        self.scraps.clear()
        self.medkits.clear()
        self.particles.clear()
        self.shockwaves.clear()
        self.traps.clear()
        self.crates.clear()

        self.boss = None
        self.room = self.room_number_for(self.current_cell)
        if self.current_cell == self.boss_cell:
            self.room_type = "boss"
        else:
            self.room_type = self.room_types.get(self.current_cell)
            if self.room_type is None:
                self.room_type = random.choice(["combat", "combat", "elite", "supply", "trap"])
                self.room_types[self.current_cell] = self.room_type
        self.final_boss = None
        if self.current_cell not in self.room_obstacles:
            self.room_obstacles[self.current_cell] = self.generate_room_obstacles(self.current_cell)
        self.obstacles = [pygame.Rect(*r) for r in self.room_obstacles[self.current_cell]]
        self.exit_open = self.current_cell in self.cleared_cells
        self.level_exit_open = (self.current_cell == self.boss_cell and self.exit_open)
        self.door_open = self.current_cell in self.cleared_cells
        self.door_rects = {}
        if self.door_open:
            self.build_door_rects()
        self.transition_timer = 0
        self.transition_side = None
        # Не даём повторно сработать двери сразу после появления у противоположной стены.
        self.door_lock_timer = 0.45 if self.entry_side is not None else 0.0
        # Блокируем дверь, через которую вошли, пока игрок не отойдёт от проёма.
        opposite_side = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
        self.entry_block_side = opposite_side.get(self.entry_side)
        self.player.reset_position()
        self.visited_cells.add(self.current_cell)

        # Вход в комнату происходит с противоположной стороны от двери.
        if self.entry_side == "top":
            self.player.x = ROOM_X + ROOM_W/2
            self.player.y = ROOM_Y + ROOM_H - WALL_SIZE - self.player.radius - 76
        elif self.entry_side == "bottom":
            self.player.x = ROOM_X + ROOM_W/2
            self.player.y = ROOM_Y + WALL_SIZE + self.player.radius + 76
        elif self.entry_side == "left":
            self.player.x = ROOM_X + ROOM_W - WALL_SIZE - self.player.radius - 76
            self.player.y = ROOM_Y + ROOM_H/2
        elif self.entry_side == "right":
            self.player.x = ROOM_X + WALL_SIZE + self.player.radius + 76
            self.player.y = ROOM_Y + ROOM_H/2
        self.entry_side = None

        # Защита от старых/неудачных сохранённых препятствий, которые могут
        # перекрыть точку появления и визуально закрыть спрайт игрока.
        if self.point_blocked_by_obstacle(self.player.x, self.player.y, self.player.radius):
            spawn_x, spawn_y = self.player.x, self.player.y
            found_spawn = False
            for step in range(1, 13):
                for ox, oy in ((0, -step*24), (step*24, 0), (0, step*24), (-step*24, 0),
                               (step*24, -step*24), (step*24, step*24),
                               (-step*24, step*24), (-step*24, -step*24)):
                    tx = clamp(spawn_x + ox, ROOM_X + WALL_SIZE + self.player.radius,
                               ROOM_X + ROOM_W - WALL_SIZE - self.player.radius)
                    ty = clamp(spawn_y + oy, ROOM_Y + WALL_SIZE + self.player.radius,
                               ROOM_Y + ROOM_H - WALL_SIZE - self.player.radius)
                    if not self.point_blocked_by_obstacle(tx, ty, self.player.radius):
                        self.player.x, self.player.y = tx, ty
                        found_spawn = True
                        break
                if found_spawn:
                    break

        # Уже зачищенная комната не создаёт врагов, ловушки и награды заново.
        # Это ключевое правило room-based roguelike: состояние комнаты сохраняется.
        if self.current_cell in self.cleared_cells:
            self.room_states.pop(self._room_state_key(), None)
            self.show_message("ЗАЧИЩЕННАЯ КОМНАТА", 1.5)
            return

        saved_room_state = self.room_states.get(self._room_state_key())
        if saved_room_state and self.restore_room_state(saved_room_state):
            self.show_message("ВОЗВРАЩЕНИЕ В КОМНАТУ", 1.5)
            return

        if self.current_cell == self.boss_cell:
            self.boss = MiniBoss(self.level)

        base = 3 + self.level // 2 + self.room
        types = ["scout", "scout", "kamikaze"]
        # В поздней игре разведчики встречаются реже, а опасные классы — чаще.
        if self.level >= 4:
            types.remove("scout")
        if self.level >= 8:
            types.remove("scout") if "scout" in types else None
            types += ["kamikaze"]
        if self.level >= 2:
            types += ["gunner"]
        if self.level >= 3:
            types += ["robot"]
        if self.level >= 6:
            types += ["robot", "gunner"]
        if self.level >= 4:
            types += ["sniper"]
        if self.level >= 5:
            types += ["shield"]
        if self.level >= 6:
            types += ["lancer"]
        if self.level >= 7:
            types += ["heavy"]

        count = base
        if self.level >= 4:
            count += 1
        if self.level >= 8:
            count += 1
        if self.current_cell == self.boss_cell:
            count = 4 + self.level // 2
        elif self.room_type == "elite":
            count += 3 + self.level // 2
        elif self.room_type == "supply":
            count = max(2, count - 2)
        elif self.room_type == "trap":
            count = max(2, count - 1)

        for _ in range(count):
            x, y = self.random_spawn()
            self.enemies.append(Enemy(random.choice(types), x, y, self.level))

        if self.room_type == "supply":
            for _ in range(3):
                x, y = self.random_inside()
                self.crates.append(SupplyCrate(x, y))
        elif self.room_type == "trap":
            for _ in range(6 + self.level // 2):
                x, y = self.random_inside()
                self.traps.append(Trap(x, y))
        elif self.room_type == "elite":
            self.player.scrap += 2

        if random.random() < .35:
            x, y = self.random_spawn()
            self.medkits.append(Medkit(x, y))

        kind_text = "БОСС" if self.current_cell == self.boss_cell else self.room_type.upper()
        self.show_message(
            f"УРОВЕНЬ {self.level}  •  КОМНАТА {self.room}/{self.level_room_count}  •  {kind_text}",
            2
        )

    def generate_room_obstacles(self, cell):
        """Создаёт постоянную для этой комнаты схему укрытий и обломков."""
        # Генератор с отдельным seed: одна и та же комната не меняет планировку
        # при повторном посещении или после загрузки сохранения.
        rng = random.Random(self.level * 1000003 + cell[0] * 9176 + cell[1] * 6113)
        candidates = [
            (ROOM_X + 135, ROOM_Y + 125, 58, 52),
            (ROOM_X + ROOM_W - 195, ROOM_Y + 128, 62, 48),
            (ROOM_X + 132, ROOM_Y + ROOM_H - 180, 54, 62),
            (ROOM_X + ROOM_W - 205, ROOM_Y + ROOM_H - 178, 64, 54),
            (ROOM_X + 230, ROOM_Y + 105, 46, 58),
            (ROOM_X + ROOM_W - 280, ROOM_Y + ROOM_H - 112, 52, 44),
        ]
        rng.shuffle(candidates)
        count = rng.randint(2, 4)
        chosen = []
        for x, y, w, h in candidates:
            rect = pygame.Rect(x, y, w, h)
            # Оставляем широкие коридоры по центру и не перекрываем двери.
            center_x = ROOM_X + ROOM_W // 2
            center_y = ROOM_Y + ROOM_H // 2
            if abs(rect.centerx - center_x) < 95 or abs(rect.centery - center_y) < 78:
                continue
            if any(rect.inflate(28, 28).colliderect(other) for other in chosen):
                continue
            chosen.append(rect)
            if len(chosen) >= count:
                break
        return [(r.x, r.y, r.width, r.height) for r in chosen]

    def point_blocked_by_obstacle(self, x, y, radius=0):
        probe = pygame.Rect(int(x-radius), int(y-radius), max(1, int(radius*2)), max(1, int(radius*2)))
        if any(obstacle.colliderect(probe) for obstacle in self.obstacles):
            return True
        # In the final arena, living cover blocks enemies and pathfinding as well.
        if getattr(self, "state", None) == "final_boss":
            return any(cover["hp"] > 0 and cover["rect"].colliderect(probe)
                       for cover in getattr(self, "boss_cover", []))
        return False

    def resolve_player_obstacles(self, old_x, old_y):
        """Надёжная покоординатная коллизия: игрок не застревает внутри укрытий."""
        target_x, target_y = self.player.x, self.player.y
        radius = self.player.radius

        # Возвращаемся в гарантированно известную позицию до перемещения.
        self.player.x, self.player.y = old_x, old_y

        # Сначала пробуем горизонтальное движение отдельно.
        if not self.point_blocked_by_obstacle(target_x, old_y, radius):
            self.player.x = target_x

        # Затем вертикальное движение с уже принятым горизонтальным смещением.
        if not self.point_blocked_by_obstacle(self.player.x, target_y, radius):
            self.player.y = target_y

        # Если старая позиция оказалась внутри препятствия (например, после
        # загрузки старого сохранения), ищем ближайшее свободное место.
        if self.point_blocked_by_obstacle(self.player.x, self.player.y, radius):
            for step in range(1, 9):
                for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0),
                               (1, -1), (1, 1), (-1, 1), (-1, -1)):
                    nx = old_x + dx * step * 5
                    ny = old_y + dy * step * 5
                    if not self.point_blocked_by_obstacle(nx, ny, radius):
                        self.player.x, self.player.y = nx, ny
                        return

    def find_enemy_waypoint(self, enemy):
        """Find the first waypoint on a short grid route around obstacles using BFS."""
        cell_size = 32
        left = ROOM_X + WALL_SIZE + enemy.radius + 2
        top = ROOM_Y + WALL_SIZE + enemy.radius + 2
        right = ROOM_X + ROOM_W - WALL_SIZE - enemy.radius - 2
        bottom = ROOM_Y + ROOM_H - WALL_SIZE - enemy.radius - 2
        cols = max(1, int((right - left) // cell_size) + 1)
        rows = max(1, int((bottom - top) // cell_size) + 1)

        def cell_at(x, y):
            return (
                max(0, min(cols - 1, int((x - left) / cell_size))),
                max(0, min(rows - 1, int((y - top) / cell_size))),
            )

        def center(cell):
            return (left + cell[0] * cell_size + cell_size / 2,
                    top + cell[1] * cell_size + cell_size / 2)

        start = cell_at(enemy.x, enemy.y)
        goal = cell_at(self.player.x, self.player.y)
        if start == goal:
            return None

        def walkable(cell):
            x, y = center(cell)
            return not self.point_blocked_by_obstacle(x, y, enemy.radius)

        # If the player stands behind cover, aim for the nearest reachable cell
        # around their position rather than attempting to enter a blocked cell.
        if not walkable(goal):
            alternatives = []
            for ox, oy in ((0, -1), (1, 0), (0, 1), (-1, 0),
                           (1, -1), (1, 1), (-1, 1), (-1, -1)):
                candidate = (goal[0] + ox, goal[1] + oy)
                if 0 <= candidate[0] < cols and 0 <= candidate[1] < rows and walkable(candidate):
                    alternatives.append(candidate)
            if not alternatives:
                return None
            goal = min(alternatives, key=lambda c: math.hypot(c[0] - start[0], c[1] - start[1]))

        queue = deque([start])
        came_from = {start: None}
        directions = ((0, -1), (1, 0), (0, 1), (-1, 0),
                      (1, -1), (1, 1), (-1, 1), (-1, -1))
        while queue:
            current = queue.popleft()
            if current == goal:
                break
            for ox, oy in directions:
                nxt = (current[0] + ox, current[1] + oy)
                if not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                    continue
                if nxt in came_from or not walkable(nxt):
                    continue
                # Prevent diagonal corner-cutting through two touching obstacles.
                if ox and oy:
                    if not walkable((current[0] + ox, current[1])) or not walkable((current[0], current[1] + oy)):
                        continue
                came_from[nxt] = current
                queue.append(nxt)

        if goal not in came_from:
            return None
        step = goal
        while came_from[step] is not None and came_from[step] != start:
            step = came_from[step]
        if came_from[step] is None:
            return None
        return center(step)

    def resolve_enemy_obstacles(self, enemy, old_x, old_y):
        """Slide along cover, and use a grid route if both movement axes are blocked."""
        target_x, target_y = enemy.x, enemy.y
        radius = enemy.radius
        enemy.path_cache_timer = max(0.0, enemy.path_cache_timer - 1.0 / FPS)
        enemy.x, enemy.y = old_x, old_y

        # Try horizontal and vertical movement separately, like the player collision.
        moved_x = False
        moved_y = False
        if not self.point_blocked_by_obstacle(target_x, old_y, radius):
            enemy.x = target_x
            moved_x = abs(target_x - old_x) > 0.01
        if not self.point_blocked_by_obstacle(enemy.x, target_y, radius):
            enemy.y = target_y
            moved_y = abs(target_y - old_y) > 0.01

        # When cover blocks both axes, find a route around it instead of pushing
        # against the same obstacle every frame. Pathfinding only runs in this case.
        blocked_x = abs(target_x - old_x) > 0.01 and not moved_x
        blocked_y = abs(target_y - old_y) > 0.01 and not moved_y
        if blocked_x and blocked_y:
            waypoint = enemy.path_cache_waypoint if enemy.path_cache_timer > 0 else None
            if waypoint is None:
                waypoint = self.find_enemy_waypoint(enemy)
                enemy.path_cache_waypoint = waypoint
                enemy.path_cache_timer = 0.22 if waypoint else 0.08
            if waypoint:
                if math.hypot(waypoint[0] - enemy.x, waypoint[1] - enemy.y) < 18:
                    enemy.path_cache_timer = 0.0
                    enemy.path_cache_waypoint = None
                wx, wy = waypoint[0] - enemy.x, waypoint[1] - enemy.y
                length = math.hypot(wx, wy) or 1.0
                step = min(enemy.speed * 0.8 * (1.0 / FPS), length)
                nx = enemy.x + wx / length * step
                ny = enemy.y + wy / length * step
                if not self.point_blocked_by_obstacle(nx, enemy.y, radius):
                    enemy.x = nx
                if not self.point_blocked_by_obstacle(enemy.x, ny, radius):
                    enemy.y = ny

        # If the old position is no longer valid (for example after crowd separation),
        # nudge the drone to the nearest free position around the obstacle.
        if self.point_blocked_by_obstacle(enemy.x, enemy.y, radius):
            for step in range(1, 9):
                candidates = ((0, -1), (1, 0), (0, 1), (-1, 0),
                              (1, -1), (1, 1), (-1, 1), (-1, -1))
                found = False
                for ox, oy in candidates:
                    nx = enemy.x + ox * step * 5
                    ny = enemy.y + oy * step * 5
                    nx = clamp(nx, ROOM_X + WALL_SIZE + radius,
                               ROOM_X + ROOM_W - WALL_SIZE - radius)
                    ny = clamp(ny, ROOM_Y + WALL_SIZE + radius,
                               ROOM_Y + ROOM_H - WALL_SIZE - radius)
                    if not self.point_blocked_by_obstacle(nx, ny, radius):
                        enemy.x, enemy.y = nx, ny
                        found = True
                        break
                if found:
                    break

    def random_inside(self):
        """Возвращает безопасную точку внутри комнаты, подальше от игрока."""
        for _ in range(50):
            x = random.randint(ROOM_X + 90, ROOM_X + ROOM_W - 90)
            y = random.randint(ROOM_Y + 90, ROOM_Y + ROOM_H - 90)
            if dist(x, y, self.player.x, self.player.y) > 170 and not self.point_blocked_by_obstacle(x, y, 24):
                return x, y

        return ROOM_X + ROOM_W // 2, ROOM_Y + ROOM_H // 2

    def random_spawn(self):
        for _ in range(50):
            side = random.choice(["top", "bottom", "left", "right"])

            if side == "top":
                x = random.randint(ROOM_X+60, ROOM_X+ROOM_W-60)
                y = ROOM_Y+55
            elif side == "bottom":
                x = random.randint(ROOM_X+60, ROOM_X+ROOM_W-60)
                y = ROOM_Y+ROOM_H-55
            elif side == "left":
                x = ROOM_X+55
                y = random.randint(ROOM_Y+60, ROOM_Y+ROOM_H-60)
            else:
                x = ROOM_X+ROOM_W-55
                y = random.randint(ROOM_Y+60, ROOM_Y+ROOM_H-60)

            if dist(x, y, self.player.x, self.player.y) > 220 and not self.point_blocked_by_obstacle(x, y, 30):
                return x, y

        return ROOM_X+60, ROOM_Y+60

    # ---------------- UI ----------------

    def show_message(self, message, seconds=2):
        self.message = message
        self.message_timer = seconds

    # ---------------- ROOM PROGRESSION ----------------

    def room_is_clear(self):
        return not self.enemies and self.boss is None

    def build_door_rects(self):
        """Обновляет активные двери по соседним комнатам карты."""
        all_doors = {
            "top": pygame.Rect(ROOM_X + ROOM_W//2 - 48, ROOM_Y + WALL_SIZE - 2, 96, 48),
            "bottom": pygame.Rect(ROOM_X + ROOM_W//2 - 48, ROOM_Y + ROOM_H - WALL_SIZE - 46, 96, 48),
            "left": pygame.Rect(ROOM_X + WALL_SIZE - 2, ROOM_Y + ROOM_H//2 - 48, 48, 96),
            "right": pygame.Rect(ROOM_X + ROOM_W - WALL_SIZE - 46, ROOM_Y + ROOM_H//2 - 48, 48, 96),
        }
        neighbors = self.neighbors_of(self.current_cell)
        self.door_rects = {side: rect for side, rect in all_doors.items() if side in neighbors}

    def open_exit(self):
        self.exit_open = True
        self.door_open = True
        if self.current_cell == self.boss_cell:
            self.level_exit_open = True
        self.build_door_rects()

        # Небольшая награда за зачистку.
        # Награда выдаётся только один раз.
        if self.current_cell not in self.cleared_cells:
            self.cleared_cells.add(self.current_cell)
            self.room_states.pop(self._room_state_key(), None)
            self.player.scrap += random.randint(2, 5)
        self.show_message("КОМНАТА ЗАЧИЩЕНА — ДВЕРИ ОТКРЫТЫ", 2.5)
        self.save()

    def begin_room_transition(self, side):
        if not self.door_open or self.transition_timer > 0:
            return
        self.transition_side = side
        self.transition_timer = .24
        self.entry_side = side
        self.show_message("ПЕРЕХОД...", .3)

    def begin_level_transition(self):
        """Запускает переход только через отдельный выход после босса."""
        if not self.level_exit_open or self.transition_timer > 0:
            return
        self.transition_side = "level_exit"
        self.transition_timer = .35
        self.entry_side = None
        self.show_message("ПЕРЕХОД НА СЛЕДУЮЩИЙ УРОВЕНЬ...", .35)

    def door_side_at_player(self):
        if self.door_lock_timer > 0 or not self.door_open:
            return None

        # Не разрешаем мгновенно вернуться через ту же дверь. Блокировка
        # снимается только после того, как персонаж отошёл внутрь комнаты.
        if self.entry_block_side:
            side = self.entry_block_side
            if side == "left" and self.player.x > ROOM_X + WALL_SIZE + 115:
                self.entry_block_side = None
            elif side == "right" and self.player.x < ROOM_X + ROOM_W - WALL_SIZE - 115:
                self.entry_block_side = None
            elif side == "top" and self.player.y > ROOM_Y + WALL_SIZE + 115:
                self.entry_block_side = None
            elif side == "bottom" and self.player.y < ROOM_Y + ROOM_H - WALL_SIZE - 115:
                self.entry_block_side = None

        for side, rect in self.door_rects.items():
            if side == self.entry_block_side:
                continue
            # Игрок может входить в проём краем модели; небольшой запас убирает "мёртвые" двери.
            if rect.inflate(self.player.radius * 2 + 12, self.player.radius * 2 + 12).collidepoint(self.player.x, self.player.y):
                return side
        return None

    def next_room(self):
        if not self.exit_open:
            return

        side = self.transition_side

        # На следующий уровень ведёт отдельный портал в комнате босса.
        # Обычные двери из комнаты босса остаются обычными переходами по карте.
        if side == "level_exit":
            if self.current_cell != self.boss_cell or not self.level_exit_open:
                return
            self.rooms_cleared += 1
            if self.level >= TOTAL_LEVELS:
                self.start_final_boss()
                return
            self.level += 1
            self.best_level = max(self.best_level, self.level)
            self.generate_level_map()
            self.prepare_shop()
            self.save()
            return

        neighbors = self.neighbors_of(self.current_cell)
        target = neighbors.get(side)
        if target is None:
            return

        # Сначала меняем комнату и размещаем игрока у правильного входа,
        # только затем сохраняем. Иначе в файл попадали координаты из старой
        # комнаты вместе с координатами новой, что могло ломать продолжение.
        self.capture_room_state()
        self.rooms_cleared += 1
        self.current_cell = target
        self.room = self.room_number_for(self.current_cell)
        self.load_room()
        self.save()

    # ---------------- ROOM MAP ----------------

    # ---------------- SHOP ----------------

    def prepare_shop(self):
        self.shop_options = [
            ("Полевой медик", "heal", 10, "Восстановить 35 HP"),
            ("Бронепластины", "hp", 20, "Макс. HP +20"),
            ("Усиленный ствол", "damage", 25, "Урон +1"),
            ("Быстрый затвор", "fire", 30, "Скорострельность +10%"),
            ("Лёгкий каркас", "speed", 20, "Скорость +20"),
            ("Керамика", "armor", 35, "Броня +1"),
        ]
        self.shop_selected = 0
        self.state = "shop"
        self.show_message("ТОРГОВЕЦ: потрать запчасти перед следующим уровнем", 3)

    def buy_shop_item(self):
        if not self.shop_options:
            return

        name, kind, cost, description = self.shop_options[self.shop_selected]
        if self.player.scrap < cost:
            self.show_message(f"НЕ ХВАТАЕТ ЗАПЧАСТЕЙ: нужно {cost}", 2)
            return

        self.player.scrap -= cost

        if kind == "heal":
            self.player.hp = min(self.player.max_hp, self.player.hp + 35)
        elif kind == "hp":
            self.player.max_hp += 20
            self.player.hp += 20
        elif kind == "damage":
            self.player.damage += 1
        elif kind == "fire":
            self.player.fire_delay = max(.055, self.player.fire_delay * .9)
        elif kind == "speed":
            self.player.speed += 20
        elif kind == "armor":
            self.player.armor += 1

        self.save()
        self.show_message(f"КУПЛЕНО: {name} — {description}", 2)

    def leave_shop(self):
        self.prepare_upgrade()

    # ---------------- UPGRADES ----------------

    def prepare_upgrade(self):
        pool = [
            ("Силовой ствол", "damage", "Урон +2"),
            ("Быстрый затвор", "fire", "Скорострельность +20%"),
            ("Военная броня", "hp", "Макс. HP +30"),
            ("Двигатель", "speed", "Скорость +35"),
            ("Двойной выстрел", "multi", "Ещё одна пуля за выстрел"),
            ("Керамическая броня", "armor", "Получаемый урон -1"),
            ("Боевые импланты", "crit", "Шанс критического урона +10%"),
        ]

        self.upgrade_options = random.sample(pool, 3)
        self.state = "upgrade"
        self.upgrade_selected = 0

    def choose_upgrade(self):
        if not self.upgrade_options:
            return

        _, kind, description = self.upgrade_options[self.upgrade_selected]

        if kind == "damage":
            self.player.damage += 2
        elif kind == "fire":
            self.player.fire_delay = max(.07, self.player.fire_delay * .8)
        elif kind == "hp":
            self.player.max_hp += 30
            self.player.hp = min(self.player.max_hp, self.player.hp + 30)
        elif kind == "speed":
            self.player.speed += 35
        elif kind == "multi":
            self.player.multishot = min(5, self.player.multishot + 1)
        elif kind == "armor":
            self.player.armor += 1
        elif kind == "crit":
            self.player.crit_chance = min(.6, self.player.crit_chance + .10)

        self.show_message(f"УЛУЧШЕНИЕ: {description}", 2)
        # После выбора бесплатного улучшения обязательно закрываем экран выбора.
        self.state = "playing"
        self.upgrade_options = []
        self.load_room()
        self.show_pickup_feedback(self.player.x, self.player.y,
                                  "УЛУЧШЕНИЕ!", CYAN, 18)
        self.save()

    def continue_without_upgrade(self):
        """Позволяет покинуть экран бесплатного улучшения без выбора бонуса."""
        if self.state != "upgrade":
            return
        self.upgrade_options = []
        self.state = "playing"
        self.load_room()
        self.save()
        self.show_message("ПРОДОЛЖАЕМ БЕЗ УЛУЧШЕНИЯ", 2)

    # ---------------- BOSS REWARDS ----------------

    def prepare_boss_reward(self):
        """Offer a choice of three powerful rewards after defeating a mini-boss."""
        pool = [
            ("ЯДРО ПЕРЕГРУЗКИ", "damage", "Урон оружия +4", ORANGE),
            ("РЕМКОМПЛЕКТ", "repair", "Восстановить 50 HP и +10 к максимуму", GREEN),
            ("ФАЗОВЫЙ ДВИГАТЕЛЬ", "engine", "Скорость +35, броня +1", CYAN),
            ("УСИЛЕННЫЙ ЗАТВОР", "fire", "Скорострельность +25%", YELLOW),
            ("КЕРАМИЧЕСКИЙ ЩИТ", "armor", "Броня +2", PURPLE),
            ("КРИТИЧЕСКИЙ МОДУЛЬ", "crit", "Шанс критического урона +15%", RED),
            ("ЭЛЕКТРОДУГИ", "electric", "Пули цепляются к соседнему врагу", CYAN),
            ("ЗАЖИГАТЕЛЬНЫЕ ПАТРОНЫ", "fire_rounds", "Враги горят после попадания", ORANGE),
            ("ПРОБОЙНИК", "piercing", "Пули пробивают до 3 врагов", PURPLE),
        ]
        self.boss_reward_options = random.sample(pool, 3)
        self.boss_reward_selected = 0
        self.state = "boss_reward"
        self.show_message("БОСС УНИЧТОЖЕН — ВЫБЕРИ НАГРАДУ", 3)

    def choose_boss_reward(self):
        if self.state != "boss_reward" or not self.boss_reward_options:
            return
        name, kind, description, color = self.boss_reward_options[self.boss_reward_selected]
        if kind == "damage":
            self.player.damage += 4
        elif kind == "repair":
            self.player.max_hp += 10
            self.player.hp = min(self.player.max_hp, self.player.hp + 50)
        elif kind == "engine":
            self.player.speed += 35
            self.player.armor += 1
        elif kind == "fire":
            self.player.fire_delay = max(.06, self.player.fire_delay * .75)
        elif kind == "armor":
            self.player.armor += 2
        elif kind == "crit":
            self.player.crit_chance = min(.65, self.player.crit_chance + .15)
        elif kind == "electric":
            self.player.electric_rounds = True
            self.player.incendiary_rounds = False
            self.player.piercing_rounds = False
        elif kind == "fire_rounds":
            self.player.incendiary_rounds = True
            self.player.electric_rounds = False
            self.player.piercing_rounds = False
        elif kind == "piercing":
            self.player.piercing_rounds = True
            self.player.electric_rounds = False
            self.player.incendiary_rounds = False
        self.boss_reward_options = []
        self.state = "playing"
        self.show_pickup_feedback(self.player.x, self.player.y, "БОСС: НАГРАДА!", color, 22)
        self.show_message(f"НАГРАДА: {name} — {description}", 3)
        self.save()

    # ---------------- DAMAGE ----------------

    def damage_player(self, amount):
        # Щит полностью блокирует урон, пока активен.
        if self.player.shield_timer > 0:
            self.spawn_particles(self.player.x, self.player.y, CYAN, 5)
            return

        if self.player.take_damage(amount):
            self.hurt_flash_timer = 0.22
            self.spawn_particles(
                self.player.x, self.player.y, RED, 7
            )
            self.shockwaves.append(Shockwave(
                self.player.x, self.player.y, RED, max_radius=34, duration=.18, width=3
            ))

        if self.player.hp <= 0:
            self.state = "gameover"
            self.record_run(victory=False)
            self.save()

    def use_shield(self):
        """Временно блокирует весь входящий урон; затем уходит на перезарядку."""
        if self.player.shield_cooldown and self.player.shield_timer <= 0:
            # shield_cooldown — длина перезарядки, shield_timer — оставшееся время защиты.
            if getattr(self.player, "shield_ready", True):
                self.player.shield_timer = self.player.shield_duration
                self.player.shield_ready = False
                self.player.shield_cooldown_timer = self.player.shield_cooldown
                self.show_message("ЭНЕРГОЩИТ АКТИВЕН: 2.5 СЕКУНДЫ", 1.5)
                self.spawn_particles(self.player.x, self.player.y, CYAN, 14)
            else:
                self.show_message(f"ЩИТ: {self.player.shield_cooldown_timer:.1f} СЕК.", .7)

    def throw_grenade(self):
        """Взрыв вокруг игрока наносит урон всем обычным врагам рядом."""
        if self.player.grenade_timer > 0:
            self.show_message(f"ГРАНАТА: {self.player.grenade_timer:.1f} СЕК.", .7)
            return

        gx, gy = self.player.x, self.player.y
        radius = 175
        damage = 35 + self.player.damage * 4
        hit_count = 0
        for enemy in self.enemies:
            if not enemy.dead and dist(gx, gy, enemy.x, enemy.y) <= radius + enemy.radius:
                enemy.hp -= damage
                hit_count += 1
                self.spawn_particles(enemy.x, enemy.y, ORANGE, 10)
                if enemy.hp <= 0:
                    enemy.dead = True
                    self.player.kills += 1
                    self.player.scrap += random.randint(2, 5)
                    # Граната уничтожает дрона с более крупной вспышкой,
                    # чтобы взрыв ощущался сильнее обычного попадания.
                    self.spawn_particles(enemy.x, enemy.y, enemy.color, 20)
                    self.spawn_particles(enemy.x, enemy.y, ORANGE, 10)
                    self.shockwaves.append(Shockwave(
                        enemy.x, enemy.y, ORANGE,
                        max_radius=54 if enemy.kind in ("heavy", "shield") else 40,
                        duration=.28, width=3
                    ))

        if self.boss and not self.boss.dead and dist(gx, gy, self.boss.x, self.boss.y) <= radius + getattr(self.boss, "radius", 45):
            self.boss.hp -= damage
            hit_count += 1
            self.spawn_particles(self.boss.x, self.boss.y, ORANGE, 18)
            if self.boss.hp <= 0:
                self.boss.dead = True
                self.player.scrap += 8
                self.spawn_particles(self.boss.x, self.boss.y, RED, 30)
                self.spawn_particles(self.boss.x, self.boss.y, ORANGE, 24)
                self.shockwaves.append(Shockwave(
                    self.boss.x, self.boss.y, RED,
                    max_radius=105, duration=.48, width=5
                ))

        self.spawn_particles(gx, gy, ORANGE, 28)
        self.player.grenade_timer = self.player.grenade_cooldown
        self.show_message(f"ГРАНАТА! УРОН {damage} · ЦЕЛЕЙ: {hit_count}", 1.5)

    # ---------------- PARTICLES ----------------

    def spawn_particles(self, x, y, color, count=8):
        for _ in range(count):
            self.particles.append(Particle(x, y, color))

    def show_pickup_feedback(self, x, y, label, color=CYAN, intensity=10):
        """Показывает вспышку, кольцо и плавающую подпись за полученную награду."""
        intensity = max(4, min(20, int(intensity)))
        self.spawn_particles(x, y, color, intensity)
        self.shockwaves.append(Shockwave(
            x, y, color, max_radius=22 + intensity * 2,
            duration=0.24, width=2
        ))
        self.damage_texts.append(FloatingPickupText(x, y - 16, label, color))

    # ---------------- UPDATE ----------------

    def update(self, dt):
        if self.state == "paused":
            return
        if self.state == "playing":
            self.update_playing(dt)
        elif self.state == "boss":
            self.update_boss(dt)
        elif self.state == "final_boss":
            self.update_final_boss(dt)

        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        for label in self.damage_texts:
            label.update(dt)
        self.damage_texts = [label for label in self.damage_texts if label.life > 0]
        for effect in self.shockwaves:
            effect.update(dt)
        self.shockwaves = [effect for effect in self.shockwaves if effect.life > 0]

        self.message_timer = max(0, self.message_timer - dt)
        self.hurt_flash_timer = max(0.0, self.hurt_flash_timer - dt)

    def player_controls(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update(keys, dt)

        # Стрельба стрелками.
        dx = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
        dy = int(keys[pygame.K_DOWN]) - int(keys[pygame.K_UP])

        if dx or dy:
            self.player.shoot(dx, dy, self.bullets)

    def update_playing(self, dt):
        if self.transition_timer > 0:
            self.transition_timer -= dt
            if self.transition_timer <= 0:
                self.transition_timer = 0
                self.next_room()
            return
        self.door_lock_timer = max(0.0, self.door_lock_timer - dt)
        old_player_x, old_player_y = self.player.x, self.player.y
        self.player_controls(dt)
        self.resolve_player_obstacles(old_player_x, old_player_y)

        for b in self.bullets:
            b.update(dt)
            if any(obstacle.collidepoint(int(b.x), int(b.y)) for obstacle in self.obstacles):
                b.life = 0

        for e in self.enemies:
            old_enemy_x, old_enemy_y = e.x, e.y
            e.update(self.player, self.bullets, dt, self.level, self.enemies)
            self.resolve_enemy_obstacles(e, old_enemy_x, old_enemy_y)
        separate_enemies(self.enemies, self.point_blocked_by_obstacle)
        # Separation can push a drone slightly into cover, so resolve once more.
        for e in self.enemies:
            self.resolve_enemy_obstacles(e, e.x, e.y)
            if not e.dead and e.burn_timer > 0:
                e.burn_timer = max(0.0, e.burn_timer - dt)
                e.burn_tick -= dt
                if e.burn_tick <= 0 and e.burn_timer > 0:
                    e.burn_tick = 0.45
                    burn_damage = max(1, int(e.burn_damage))
                    e.hp -= burn_damage
                    self.damage_texts.append(FloatingDamageText(
                        e.x, e.y - e.radius - 8, burn_damage, critical=False))
                    self.spawn_particles(e.x, e.y, ORANGE, 3)
                    if e.hp <= 0:
                        e.dead = True
                        self.player.kills += 1
                        data = ENEMY_DATA[e.kind]
                        self.scraps.append(Scrap(e.x, e.y, random.randint(*data["scrap"])))
                        if random.random() < .08:
                            self.medkits.append(Medkit(e.x, e.y))
                        self.spawn_particles(e.x, e.y, ORANGE, 14)

        for s in self.scraps:
            s.update(dt)
            s.attract_to(self.player.x, self.player.y, dt)

        for m in self.medkits:
            m.update(dt)

        for trap in self.traps:
            damage = trap.update(self.player, dt)
            if damage:
                self.damage_player(damage)
                self.spawn_particles(trap.x, trap.y, RED, 12)

        for crate in self.crates:
            if not crate.opened and dist(crate.x,crate.y,self.player.x,self.player.y)<42:
                crate.opened=True
                reward=random.choice(["scrap","heal","damage"])
                if reward=="scrap":
                    amount=random.randint(8,18); self.player.scrap += amount
                    self.show_pickup_feedback(crate.x, crate.y, f"+{amount} ЗАПЧ.", YELLOW, 18)
                    self.show_message(f"КОНТЕЙНЕР: +{amount} ЗАПЧАСТЕЙ",1.5)
                elif reward=="heal":
                    self.player.heal(30)
                    self.show_pickup_feedback(crate.x, crate.y, "+30 HP", GREEN, 15)
                    self.show_message("КОНТЕЙНЕР: +30 HP",1.5)
                else:
                    self.player.damage += 1
                    self.show_pickup_feedback(crate.x, crate.y, "УРОН +1", ORANGE, 15)
                    self.show_message("КОНТЕЙНЕР: УРОН +1",1.5)

        if self.boss:
            self.boss.update(
                self.player, self.bullets, self.enemies, dt
            )
            if (not self.boss.dead and getattr(self.boss, "archetype", -1) == 3
                    and self.boss.contact_cooldown <= 0
                    and circle_hit(self.player.x, self.player.y, self.player.radius,
                                   self.boss.x, self.boss.y, self.boss.radius)):
                self.damage_player(17 + self.level)
                self.boss.contact_cooldown = 0.9

        self.handle_combat()

        self.bullets = [b for b in self.bullets if b.alive()]
        self.enemies = [e for e in self.enemies if not e.dead]

        # Открытие выхода после зачистки.
        if not self.enemies and self.boss is None and not self.exit_open:
            self.open_exit()

        # Если мини-босс умер — открыть выход.
        if self.boss and self.boss.dead and not self.exit_open:
            self.boss = None
            self.open_exit()
            # Offer a one-time choice when the room's boss is defeated.
            self.prepare_boss_reward()
            return

        # Отдельный выход на следующий уровень находится внутри комнаты босса.
        if self.level_exit_open and self.current_cell == self.boss_cell:
            if self.level_exit_rect.collidepoint(int(self.player.x), int(self.player.y)):
                self.begin_level_transition()
                return

        # В стиле Isaac: после зачистки можно войти в любую открытую обычную дверь.
        side = self.door_side_at_player()
        if side:
            self.begin_room_transition(side)
        elif self.door_open:
            # Старое управление E оставляем как дополнительный способ перехода.
            for door_side, rect in self.door_rects.items():
                if rect.inflate(24, 24).collidepoint(self.player.x, self.player.y):
                    self.show_message("Войди в светящийся дверной проём", .2)
                    break

    def handle_combat(self):
        # Пули игрока.
        for bullet in self.bullets:
            if bullet.enemy or bullet.life <= 0:
                continue

            hit_target = False

            for enemy in self.enemies:
                if enemy.dead or id(enemy) in bullet.hit_targets:
                    continue

                if circle_hit(
                    bullet.x, bullet.y, bullet.radius,
                    enemy.x, enemy.y, enemy.radius
                ):
                    damage = bullet.damage
                    if enemy.kind == "shield" and enemy.shield_active:
                        damage = max(1, int(damage * 0.35))
                    enemy.hp -= damage
                    bullet.hit_targets.add(id(enemy))
                    if bullet.explosive_radius > 0:
                        blast_x, blast_y = bullet.x, bullet.y
                        self.spawn_particles(blast_x, blast_y, ORANGE, 22)
                        self.shockwaves.append(Shockwave(
                            blast_x, blast_y, ORANGE,
                            max_radius=bullet.explosive_radius, duration=.28, width=4))
                        # The direct target receives full damage; nearby enemies take
                        # reduced splash damage. Each target is processed only once.
                        for nearby_enemy in self.enemies:
                            if (nearby_enemy is enemy or nearby_enemy.dead
                                    or id(nearby_enemy) in bullet.hit_targets):
                                continue
                            if dist(nearby_enemy.x, nearby_enemy.y, blast_x, blast_y) <= bullet.explosive_radius:
                                splash_damage = max(1, int(damage * .60))
                                if nearby_enemy.kind == "shield" and nearby_enemy.shield_active:
                                    splash_damage = max(1, int(splash_damage * .35))
                                nearby_enemy.hp -= splash_damage
                                nearby_enemy.hit_flash = .16
                                nearby_enemy.hit_pulse = .20
                                bullet.hit_targets.add(id(nearby_enemy))
                                self.damage_texts.append(FloatingDamageText(
                                    nearby_enemy.x, nearby_enemy.y - nearby_enemy.radius - 8,
                                    splash_damage, critical=False))
                                self.spawn_particles(nearby_enemy.x, nearby_enemy.y, ORANGE, 8)
                                if nearby_enemy.hp <= 0:
                                    nearby_enemy.dead = True
                                    self.player.kills += 1
                                    nearby_data = ENEMY_DATA[nearby_enemy.kind]
                                    self.scraps.append(Scrap(
                                        nearby_enemy.x, nearby_enemy.y,
                                        random.randint(*nearby_data["scrap"])))
                                    if random.random() < .08:
                                        self.medkits.append(Medkit(nearby_enemy.x, nearby_enemy.y))
                                    self.spawn_particles(nearby_enemy.x, nearby_enemy.y,
                                                         nearby_enemy.color, 16)
                    if bullet.element == "fire":
                        enemy.burn_timer = max(enemy.burn_timer, 2.7)
                        enemy.burn_tick = min(enemy.burn_tick, 0.25) if enemy.burn_tick > 0 else 0.25
                        # При сильном оружии огонь становится мощнее: синергия «Инферно».
                        burn_scale = 0.42 if self.player.damage >= 6 else 0.28
                        enemy.burn_damage = max(enemy.burn_damage, max(1, int(bullet.damage * burn_scale)))
                    if bullet.element == "electric" and not bullet.chain_used:
                        bullet.chain_used = True
                        nearby = [other for other in self.enemies
                                  if other is not enemy and not other.dead
                                  and dist(other.x, other.y, enemy.x, enemy.y) < 145]
                        if nearby:
                            chained = min(nearby, key=lambda other: dist(other.x, other.y, enemy.x, enemy.y))
                            # При шансе критического удара от 20% дуга бьёт сильнее.
                            chain_scale = 0.75 if self.player.crit_chance >= 0.20 else 0.55
                            chain_damage = max(1, int(bullet.damage * chain_scale))
                            if chained.kind == "shield" and chained.shield_active:
                                chain_damage = max(1, int(chain_damage * 0.35))
                            chained.hp -= chain_damage
                            chained.hit_flash = .12
                            self.damage_texts.append(FloatingDamageText(
                                chained.x, chained.y - chained.radius - 8, chain_damage, critical=False))
                            self.spawn_particles(chained.x, chained.y, CYAN, 8)
                            self.shockwaves.append(Shockwave(
                                chained.x, chained.y, CYAN, max_radius=27, duration=.18, width=2))
                            if chained.hp <= 0:
                                chained.dead = True
                                self.player.kills += 1
                                data = ENEMY_DATA[chained.kind]
                                self.scraps.append(Scrap(chained.x, chained.y, random.randint(*data["scrap"])))
                                if random.random() < .08:
                                    self.medkits.append(Medkit(chained.x, chained.y))
                                self.spawn_particles(chained.x, chained.y, CYAN, 14)
                    self.damage_texts.append(FloatingDamageText(
                        enemy.x, enemy.y - enemy.radius - 10, damage,
                        critical=damage >= max(4, self.player.damage * 2)
                    ))
                    enemy.hit_flash = .1
                    enemy.hit_pulse = .18
                    enemy.stun = .04
                    if bullet.pierce > 0:
                        bullet.pierce -= 1
                    else:
                        bullet.life = 0
                    hit_target = True

                    # Контрастные искры и маленькое кольцо показывают точку попадания.
                    # Щит поглощает часть урона и даёт холодные голубые искры.
                    impact_color = CYAN if enemy.kind == "shield" and enemy.shield_active else ORANGE
                    self.spawn_particles(bullet.x, bullet.y, impact_color, 6)
                    self.shockwaves.append(Shockwave(
                        bullet.x, bullet.y, impact_color,
                        max_radius=19 if enemy.kind in ("heavy", "shield") else 13,
                        duration=.13, width=2
                    ))

                    if enemy.hp <= 0:
                        enemy.dead = True
                        self.player.kills += 1

                        data = ENEMY_DATA[enemy.kind]
                        amount = random.randint(*data["scrap"])
                        self.scraps.append(
                            Scrap(enemy.x, enemy.y, amount)
                        )

                        if random.random() < .08:
                            self.medkits.append(
                                Medkit(enemy.x, enemy.y)
                            )

                        self.spawn_particles(
                            enemy.x, enemy.y, enemy.color, 18
                        )
                        self.shockwaves.append(
                            Shockwave(enemy.x, enemy.y, enemy.color,
                                      max_radius=58 if enemy.kind in ("heavy", "shield") else 38,
                                      duration=.30 if enemy.kind in ("heavy", "shield") else .22,
                                      width=4 if enemy.kind in ("heavy", "shield") else 2)
                        )
                    if bullet.life <= 0:
                        break

            # Ложные голограммы Охотника могут перехватить пулю вместо настоящего босса.
            if (self.boss and not self.boss.dead and not hit_target
                    and getattr(self.boss, "archetype", -1) == 3):
                for decoy in self.boss.hunter_decoys:
                    if decoy["life"] > 0 and circle_hit(
                            bullet.x, bullet.y, bullet.radius,
                            decoy["x"], decoy["y"], 25):
                        decoy["life"] = 0
                        bullet.life = 0
                        hit_target = True
                        self.spawn_particles(decoy["x"], decoy["y"], CYAN, 11)
                        self.shockwaves.append(Shockwave(
                            decoy["x"], decoy["y"], CYAN,
                            max_radius=34, duration=.22, width=3
                        ))
                        break

            # Попадание в мини-босса.
            if self.boss and not self.boss.dead and not hit_target:
                if circle_hit(
                    bullet.x, bullet.y, bullet.radius,
                    self.boss.x, self.boss.y, self.boss.radius
                ):
                    self.boss.hp -= bullet.damage
                    bullet.life = 0
                    # Броня босса даёт красно-оранжевую вспышку при каждом попадании.
                    self.spawn_particles(bullet.x, bullet.y, ORANGE, 7)
                    self.shockwaves.append(Shockwave(
                        bullet.x, bullet.y, RED, max_radius=22,
                        duration=.16, width=2
                    ))
                    if self.boss.hp <= 0:
                        self.boss.dead = True
                        self.player.scrap += 8
                        self.spawn_particles(
                            self.boss.x, self.boss.y, RED, 30
                        )

        # Пули врагов.
        for bullet in self.bullets:
            if not bullet.enemy or bullet.life <= 0:
                continue

            if circle_hit(
                bullet.x, bullet.y, bullet.radius,
                self.player.x, self.player.y, self.player.radius
            ):
                bullet.life = 0
                self.damage_player(bullet.damage)

        # Контакт с врагами.
        for enemy in self.enemies:
            if enemy.dead:
                continue

            if circle_hit(
                enemy.x, enemy.y, enemy.radius,
                self.player.x, self.player.y, self.player.radius
            ):
                if enemy.kind == "kamikaze":
                    self.damage_player(enemy.damage)
                    enemy.dead = True
                    self.scraps.append(
                        Scrap(enemy.x, enemy.y, random.randint(1, 3))
                    )
                    self.spawn_particles(
                        enemy.x, enemy.y, ORANGE, 24
                    )
                    self.shockwaves.append(Shockwave(
                        enemy.x, enemy.y, ORANGE, max_radius=74, duration=.34, width=5
                    ))
                else:
                    self.damage_player(6)

        # Сбор запчастей с заметной, но короткой визуальной наградой.
        remaining_scraps = []
        for scrap in self.scraps:
            if dist(scrap.x, scrap.y,
                    self.player.x, self.player.y) < 35:
                self.player.scrap += scrap.amount
                self.show_pickup_feedback(
                    scrap.x, scrap.y, f"+{scrap.amount} ЗАПЧ.", YELLOW,
                    7 + min(7, scrap.amount)
                )
            else:
                remaining_scraps.append(scrap)
        self.scraps = remaining_scraps

        # Аптечки.
        remaining_medkits = []
        for med in self.medkits:
            if dist(med.x, med.y,
                    self.player.x, self.player.y) < 35:
                self.player.heal(25)
                self.show_pickup_feedback(med.x, med.y, "+25 HP", GREEN, 12)
                self.show_message("АПТЕЧКА: +25 HP", 1.3)
            else:
                remaining_medkits.append(med)
        self.medkits = remaining_medkits

    # ---------------- FINAL BOSS ----------------

    def start_final_boss(self):
        self.state = "final_boss"
        self.bullets.clear()
        self.enemies.clear()
        self.scraps.clear()
        self.medkits.clear()
        self.player.reset_position()
        # The final arena has its own cover; don't carry over room obstacles.
        self.obstacles = []
        self.boss_cover = []
        cover_specs = (
            (ROOM_X + 145, ROOM_Y + 150, 76, 34),
            (ROOM_X + ROOM_W - 220, ROOM_Y + 150, 76, 34),
            (ROOM_X + 145, ROOM_Y + ROOM_H - 190, 76, 34),
            (ROOM_X + ROOM_W - 220, ROOM_Y + ROOM_H - 190, 76, 34),
        )
        for index, spec in enumerate(cover_specs):
            self.boss_cover.append({
                "rect": pygame.Rect(*spec),
                "hp": 62.0,
                "max_hp": 62.0,
                "index": index,
                "flash": 0.0,
            })

        self.final_boss = {
            "x": WIDTH/2,
            "y": HEIGHT/2,
            "max_hp": 600,
            "hp": 600,
            "timer": 0,
            "shoot": .7,
            "shot_warning": 0,
            "shot_target_x": WIDTH/2,
            "shot_target_y": HEIGHT/2,
            "spawn": 3,
            "burst": 2.0,
            "ring_warning": 0,
            "dash": 4.0,
            "phase": 1,
            "core_open": 0,
            "warning": 0,
            "dash_x": WIDTH/2,
            "dash_y": HEIGHT/2,
            "cross_timer": 5.0,
            "cross_warning": 0.0,
            "cross_target_x": WIDTH/2,
            "cross_target_y": HEIGHT/2,
            # Phase transitions and attack recovery intentionally create short safe windows.
            "phase_recovery": 0.0,
            # Arena-wide sweep: the red floor is dangerous; the cyan corridor is safe.
            "sweep_timer": 8.0,
            "sweep_warning": 0.0,
            "sweep_active": 0.0,
            "sweep_axis": "vertical",
            "sweep_gap_x": float(WIDTH/2),
            "sweep_gap_y": float(HEIGHT/2),
        }

        self.show_message(
            "ОГРОМНЫЙ ДРОН. Собери минимум 30 запчастей и уничтожь его!",
            5
        )

    def resolve_final_boss_cover(self, old_x, old_y):
        """Keep the player outside intact cover, allowing axis-wise sliding."""
        px, py = self.player.x, self.player.y
        radius = self.player.radius

        def blocked(x, y):
            probe = pygame.Rect(
                int(x - radius), int(y - radius),
                max(1, int(radius * 2)), max(1, int(radius * 2))
            )
            return any(c["hp"] > 0 and c["rect"].colliderect(probe)
                       for c in self.boss_cover)

        self.player.x, self.player.y = old_x, old_y
        if not blocked(px, old_y):
            self.player.x = px
        if not blocked(self.player.x, py):
            self.player.y = py

    def update_final_boss_cover_and_bullets(self, dt):
        """Update shots; intact cover stops them and can be destroyed by fire."""
        for bullet in self.bullets:
            bullet.update(dt)
            if bullet.life <= 0:
                continue
            hit_cover = None
            for cover in self.boss_cover:
                if cover["hp"] <= 0:
                    continue
                hitbox = cover["rect"].inflate(bullet.radius * 2, bullet.radius * 2)
                if hitbox.collidepoint(int(bullet.x), int(bullet.y)):
                    hit_cover = cover
                    break
            if hit_cover is not None:
                # Both sides can damage cover; player fire is slightly more effective.
                hit_cover["hp"] -= bullet.damage * (1.0 if not bullet.enemy else 0.7)
                hit_cover["flash"] = 0.12
                bullet.life = 0
                self.spawn_particles(bullet.x, bullet.y,
                                     CYAN if not bullet.enemy else ORANGE, 3)
                if hit_cover["hp"] <= 0:
                    cx, cy = hit_cover["rect"].center
                    self.spawn_particles(cx, cy, ORANGE, 20)
                    self.spawn_particles(cx, cy, CYAN, 12)
                    self.shockwaves.append(Shockwave(
                        cx, cy, ORANGE, max_radius=54, duration=0.28, width=4
                    ))
                    self.show_message("УКРЫТИЕ РАЗРУШЕНО", 0.8)

    def update_final_boss(self, dt):
        old_player_x, old_player_y = self.player.x, self.player.y
        self.player_controls(dt)
        self.resolve_final_boss_cover(old_player_x, old_player_y)

        boss = self.final_boss
        boss["timer"] += dt
        boss["shoot"] -= dt
        boss["spawn"] -= dt
        boss["burst"] -= dt
        boss["phase_recovery"] = max(0.0, boss.get("phase_recovery", 0.0) - dt)
        boss["sweep_timer"] = max(0.0, boss.get("sweep_timer", 8.0) - dt)
        previous_sweep_warning = boss.get("sweep_warning", 0.0)
        boss["sweep_warning"] = max(0.0, previous_sweep_warning - dt)
        boss["sweep_active"] = max(0.0, boss.get("sweep_active", 0.0) - dt)
        for cover in self.boss_cover:
            cover["flash"] = max(0.0, cover.get("flash", 0.0) - dt)
        previous_ring_warning = boss.get("ring_warning", 0)
        boss["ring_warning"] = max(0, previous_ring_warning - dt)
        boss["dash"] -= dt
        boss["core_open"] = max(0, boss["core_open"] - dt)
        boss["warning"] = max(0, boss["warning"] - dt)
        previous_shot_warning = boss["shot_warning"]
        boss["shot_warning"] = max(0, boss["shot_warning"] - dt)
        previous_cross_warning = boss.get("cross_warning", 0.0)
        boss["cross_warning"] = max(0.0, previous_cross_warning - dt)

        ratio = boss["hp"] / boss["max_hp"]
        old_phase = boss["phase"]
        if ratio < .66:
            boss["phase"] = 2
        if ratio < .33:
            boss["phase"] = 3
        if boss["phase"] != old_phase:
            # Entering a new stage interrupts queued attacks and grants a readable recovery window.
            boss["core_open"] = 2.35
            boss["phase_recovery"] = 2.0
            boss["shot_warning"] = 0.0
            boss["ring_warning"] = 0.0
            boss["cross_warning"] = 0.0
            boss["sweep_warning"] = 0.0
            boss["sweep_active"] = 0.0
            boss["warning"] = 0.0
            # Clear local countdown transitions too, so an old warning cannot fire
            # in the exact frame the new phase grants its recovery window.
            previous_shot_warning = 0.0
            previous_ring_warning = 0.0
            previous_cross_warning = 0.0
            previous_sweep_warning = 0.0
            boss["shoot"] = 1.25
            boss["burst"] = 3.2
            boss["dash"] = 4.3
            boss["cross_timer"] = 5.2
            boss["sweep_timer"] = 5.8
            boss["spawn"] = 3.5
            self.show_message(f"ФАЗА {boss['phase']}: БРОНЯ ПЕРЕКОНФИГУРИРОВАНА!", 2.2)
            self.spawn_particles(boss["x"], boss["y"],
                                 CYAN if boss["phase"] == 2 else PURPLE, 42)
            self.shockwaves.append(Shockwave(
                boss["x"], boss["y"], CYAN if boss["phase"] == 2 else PURPLE,
                max_radius=150, duration=0.45, width=6
            ))

        # Босс двигается по широкой траектории.
        boss["x"] = WIDTH/2 + math.cos(boss["timer"]*.45) * 300
        boss["y"] = 365 + math.sin(boss["timer"]*.7) * 130

        # В фазах 2-3 ядро периодически открывается: это короткое окно
        # повышенного урона. В остальное время корпус защищён.
        if boss["phase"] >= 2 and boss["core_open"] <= 0 and boss["burst"] <= 0:
            boss["core_open"] = 1.2
            boss["burst"] = max(2.2, 3.6 - boss["phase"]*.35)

        # Перед каждым веером босс фиксирует положение игрока и показывает линию прицеливания.
        # После короткого предупреждения выпускает снаряды в отмеченном направлении.
        if (boss["phase_recovery"] <= 0 and boss.get("sweep_warning", 0) <= 0
                and boss.get("sweep_active", 0) <= 0 and boss["shoot"] <= 0
                and boss["shot_warning"] <= 0 and previous_shot_warning <= 0):
            boss["shot_target_x"] = self.player.x
            boss["shot_target_y"] = self.player.y
            boss["shot_warning"] = .42
            boss["shoot"] = 999  # ждём завершения предупреждения

        if previous_shot_warning > 0 and boss["shot_warning"] <= 0:
            dx = boss["shot_target_x"] - boss["x"]
            dy = boss["shot_target_y"] - boss["y"]
            base = math.atan2(dy, dx)
            count = 7 if boss["phase"] == 1 else (11 if boss["phase"] == 2 else 15)
            spread = .7 if boss["phase"] == 1 else (1.1 if boss["phase"] == 2 else 1.45)
            for i in range(count):
                offset = 0 if count == 1 else -spread/2 + spread*i/(count-1)
                a = base + offset
                self.bullets.append(Bullet(
                    boss["x"], boss["y"], math.cos(a), math.sin(a),
                    13 + boss["phase"]*3, True,
                    360 + boss["phase"]*25, RED, 6
                ))
            boss["shoot"] = max(.28, .95 - boss["phase"]*.12)

        # Фаза 3: крестовой залп из отмеченной позиции. Игрок видит четыре
        # линии опасности заранее и может выйти из точки пересечения.
        if boss["phase"] >= 3:
            boss["cross_timer"] = max(0.0, boss.get("cross_timer", 5.0) - dt)
            if previous_cross_warning > 0 and boss["cross_warning"] <= 0:
                tx, ty = boss["cross_target_x"], boss["cross_target_y"]
                for base_angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
                    for spread in (-0.065, 0.065):
                        angle = base_angle + spread
                        self.bullets.append(Bullet(
                            tx, ty, math.cos(angle), math.sin(angle),
                            11 + boss["phase"] * 2, True, 375, CYAN, 5
                        ))
                self.show_message("КРЕСТОВОЙ ЗАЛП — УХОДИ С ЛИНИЙ!", 1.1)
            if (boss["phase_recovery"] <= 0 and boss.get("sweep_warning", 0) <= 0
                    and boss.get("sweep_active", 0) <= 0 and boss["cross_timer"] <= 0
                    and boss["cross_warning"] <= 0):
                boss["cross_target_x"] = float(self.player.x)
                boss["cross_target_y"] = float(self.player.y)
                boss["cross_warning"] = 0.92
                boss["cross_timer"] = 6.4

        # Фазы 2-3: перед круговым залпом появляется заметное предупреждение.
        # Это даёт игроку время отойти от босса и выбрать безопасное направление.
        if (boss["phase"] >= 2 and boss["phase_recovery"] <= 0
                and boss.get("sweep_warning", 0) <= 0 and boss.get("sweep_active", 0) <= 0
                and boss["burst"] <= 0 and boss["ring_warning"] <= 0
                and previous_ring_warning <= 0):
            boss["ring_warning"] = 0.7

        if boss["phase"] >= 2 and previous_ring_warning > 0 and boss["ring_warning"] <= 0:
            count = 12 if boss["phase"] == 2 else 18
            base = boss["timer"] * (1.4 if boss["phase"] == 2 else 2.0)
            for i in range(count):
                a = base + math.tau * i / count
                self.bullets.append(Bullet(
                    boss["x"], boss["y"], math.cos(a), math.sin(a),
                    9 + boss["phase"]*2, True, 300 + boss["phase"]*25,
                    ORANGE, 5
                ))
            boss["burst"] = 3.4 if boss["phase"] == 2 else 2.6

        # Phases 2-3: an arena-wide sweep leaves one clearly marked safe corridor.
        # The player gets 1.05s to move to the cyan gap before the red zones activate.
        if (boss["phase"] >= 2 and boss["phase_recovery"] <= 0
                and boss["sweep_timer"] <= 0 and boss["sweep_warning"] <= 0
                and boss["sweep_active"] <= 0 and previous_shot_warning <= 0
                and previous_ring_warning <= 0 and previous_cross_warning <= 0
                and boss["shot_warning"] <= 0 and boss["ring_warning"] <= 0
                and boss["cross_warning"] <= 0 and boss["warning"] <= 0):
            boss["sweep_axis"] = random.choice(("vertical", "horizontal"))
            inner_left = ROOM_X + WALL_SIZE + 24
            inner_right = ROOM_X + ROOM_W - WALL_SIZE - 24
            inner_top = ROOM_Y + WALL_SIZE + 24
            inner_bottom = ROOM_Y + ROOM_H - WALL_SIZE - 24
            if boss["sweep_axis"] == "vertical":
                target = self.player.x + random.choice((-150, 0, 150))
                boss["sweep_gap_x"] = clamp(target, inner_left + 66, inner_right - 66)
            else:
                target = self.player.y + random.choice((-115, 0, 115))
                boss["sweep_gap_y"] = clamp(target, inner_top + 66, inner_bottom - 66)
            boss["sweep_warning"] = 1.05
            boss["sweep_timer"] = 9.4 if boss["phase"] == 2 else 7.2
            boss["ring_warning"] = 0.0
            boss["cross_warning"] = 0.0
            boss["shot_warning"] = 0.0
            boss["warning"] = 0.0
            previous_ring_warning = 0.0
            previous_cross_warning = 0.0
            previous_shot_warning = 0.0
            self.show_message("АРЕНА ЗАРЯЖАЕТСЯ — ВСТАНЬ В ГОЛУБОЙ ПРОХОД!", 1.4)

        if previous_sweep_warning > 0 and boss["sweep_warning"] <= 0:
            boss["sweep_active"] = 0.68
            boss["phase_recovery"] = 1.05
            boss["core_open"] = max(boss["core_open"], 1.25)
            boss["ring_warning"] = 0.0
            boss["cross_warning"] = 0.0
            boss["shot_warning"] = 0.0
            boss["warning"] = 0.0
            previous_ring_warning = 0.0
            previous_cross_warning = 0.0
            previous_shot_warning = 0.0
            gap_half = 66
            if boss["sweep_axis"] == "vertical":
                in_safe_gap = abs(self.player.x - boss["sweep_gap_x"]) <= gap_half
            else:
                in_safe_gap = abs(self.player.y - boss["sweep_gap_y"]) <= gap_half
            if not in_safe_gap:
                self.damage_player(26 if boss["phase"] == 2 else 34)
                self.spawn_particles(self.player.x, self.player.y, RED, 18)
            self.spawn_particles(boss["x"], boss["y"], CYAN, 18)
            self.show_message("ИМПУЛЬС ПРОШЁЛ — ЯДРО ОТКРЫТО!", 1.15)

        # Фаза 3: телеграфируемый рывок — перед рывком показываем предупреждение.
        if (boss["phase"] == 3 and boss["phase_recovery"] <= 0
                and boss.get("sweep_warning", 0) <= 0 and boss.get("sweep_active", 0) <= 0
                and boss["dash"] <= 0):
            boss["dash_x"] = self.player.x
            boss["dash_y"] = self.player.y
            boss["warning"] = .65
            boss["dash"] = 4.2

        if boss["warning"] > 0 or boss["phase_recovery"] > 0:
            # The recovery window intentionally gives the player time to reposition.
            pass
        elif boss["phase"] == 3 and boss["dash"] > 3.5:
            dx = boss["dash_x"] - boss["x"]
            dy = boss["dash_y"] - boss["y"]
            d = math.hypot(dx, dy) or 1
            boss["x"] += dx/d * 360 * dt
            boss["y"] += dy/d * 360 * dt

        # Дополнительные дроны.
        if (boss["spawn"] <= 0 and boss["phase_recovery"] <= 0
                and boss.get("sweep_warning", 0) <= 0 and boss.get("sweep_active", 0) <= 0):
            for _ in range(2 + boss["phase"]):
                x = random.choice([ROOM_X+60, ROOM_X+ROOM_W-60])
                y = random.randint(ROOM_Y+100, ROOM_Y+ROOM_H-80)
                pool = ["scout", "kamikaze", "gunner"]
                if boss["phase"] >= 2:
                    pool += ["sniper"]
                if boss["phase"] >= 3:
                    pool += ["shield", "heavy", "lancer"]
                self.enemies.append(Enemy(random.choice(pool), x, y, self.level))
            boss["spawn"] = max(1.7, 5 - boss["phase"])

        self.update_final_boss_cover_and_bullets(dt)
        for e in self.enemies:
            old_enemy_x, old_enemy_y = e.x, e.y
            e.update(self.player, self.bullets, dt, self.level, self.enemies)
            self.resolve_enemy_obstacles(e, old_enemy_x, old_enemy_y)
        separate_enemies(self.enemies, self.point_blocked_by_obstacle)
        # Separation can push a drone slightly into cover, so resolve once more.
        for e in self.enemies:
            self.resolve_enemy_obstacles(e, e.x, e.y)

        self.handle_combat()

        # Урон финальному боссу. В фазах 2-3 корпус защищён, пока ядро закрыто.
        for b in self.bullets:
            if b.enemy or b.life <= 0:
                continue
            if circle_hit(b.x, b.y, b.radius, boss["x"], boss["y"], 85):
                b.life = 0
                damage = b.damage
                if boss["phase"] >= 2 and boss["core_open"] <= 0:
                    damage = max(0.2, damage * .18)
                elif boss["core_open"] > 0:
                    damage *= 1.35
                boss["hp"] -= damage
                self.spawn_particles(b.x, b.y, RED, 3)

        # Контакт с огромным дроном.
        if dist(self.player.x, self.player.y, boss["x"], boss["y"]) < 105:
            self.damage_player(20 if boss["phase"] < 3 else 28)

        self.bullets = [b for b in self.bullets if b.alive()]
        self.enemies = [e for e in self.enemies if not e.dead]
        self.collect_final_items()

        if boss["hp"] <= 0:
            if self.player.scrap >= 30:
                if not self.boss_death_fx_done:
                    self.boss_death_fx_done = True
                    self.spawn_particles(boss["x"], boss["y"], ORANGE, 65)
                    self.spawn_particles(boss["x"], boss["y"], CYAN, 35)
                    self.shockwaves.append(Shockwave(
                        boss["x"], boss["y"], ORANGE, max_radius=190, duration=.55, width=7
                    ))
                self.state = "victory"
                self.record_run(victory=True)
                self.save()
            else:
                boss["hp"] = 1
                self.show_message(f"Не хватает запчастей: {30-self.player.scrap}", 2)

    def collect_final_items(self):
        remaining = []
        dt = 1 / FPS
        for scrap in self.scraps:
            scrap.update(dt)
            scrap.attract_to(self.player.x, self.player.y, dt)
            if dist(scrap.x, scrap.y,
                    self.player.x, self.player.y) < 35:
                self.player.scrap += scrap.amount
                self.show_pickup_feedback(
                    scrap.x, scrap.y, f"+{scrap.amount} ЗАПЧ.", YELLOW,
                    7 + min(7, scrap.amount)
                )
            else:
                remaining.append(scrap)
        self.scraps = remaining

    # ---------------- DRAW ----------------

    def draw_room_background(self):
        SCREEN.fill(BG)

        pygame.draw.rect(
            SCREEN, ROOM,
            (ROOM_X, ROOM_Y, ROOM_W, ROOM_H)
        )
        pygame.draw.rect(
            SCREEN, WALL,
            (ROOM_X, ROOM_Y, ROOM_W, ROOM_H),
            WALL_SIZE
        )

        # Подложка пола: крупные панели, чтобы комнаты читались как 16-bit пиксель-арт.
        inner = pygame.Rect(ROOM_X + WALL_SIZE, ROOM_Y + WALL_SIZE,
                           ROOM_W - WALL_SIZE * 2, ROOM_H - WALL_SIZE * 2)
        pygame.draw.rect(SCREEN, (14, 18, 24), inner)

        # Цветовая маркировка типа комнаты: помогает распознавать её ещё до боя.
        room_kind = "boss" if self.current_cell == self.boss_cell else self.room_type
        room_accents = {
            "combat": ((62, 154, 184), "C"),
            "elite": ((220, 73, 58), "E"),
            "supply": ((78, 190, 112), "S"),
            "trap": ((226, 164, 54), "T"),
            "boss": ((190, 65, 205), "B"),
        }
        accent, room_symbol = room_accents.get(room_kind, ((62, 154, 184), "C"))
        # Тонкая цветная линия по внутреннему периметру, не перекрывающая игру.
        pygame.draw.rect(SCREEN, accent,
                         (inner.left + 5, inner.top + 5, inner.width - 10, inner.height - 10), 2)
        # Четыре небольших сигнальных индикатора у углов комнаты.
        for lx, ly in ((inner.left + 13, inner.top + 13),
                       (inner.right - 13, inner.top + 13),
                       (inner.left + 13, inner.bottom - 13),
                       (inner.right - 13, inner.bottom - 13)):
            pygame.draw.rect(SCREEN, (8, 10, 15), (lx - 5, ly - 5, 10, 10))
            pygame.draw.rect(SCREEN, accent, (lx - 3, ly - 3, 6, 6))
        # Символ типа комнаты расположен в небольшом техническом маркере у верхнего края.
        marker = pygame.Rect(ROOM_X + ROOM_W // 2 - 17, ROOM_Y + WALL_SIZE + 12, 34, 25)
        pygame.draw.rect(SCREEN, (7, 10, 15), marker, border_radius=3)
        pygame.draw.rect(SCREEN, accent, marker, 2, border_radius=3)
        text(SCREEN, room_symbol, SMALL, accent, marker.centerx, marker.centery, True)

        for x in range(ROOM_X + 42, ROOM_X + ROOM_W - WALL_SIZE, 70):
            pygame.draw.line(SCREEN, GRID, (x, inner.top), (x, inner.bottom), 2)
            for y in range(inner.top + 18, inner.bottom - 10, 70):
                pygame.draw.rect(SCREEN, (20, 25, 32), (x + 5, y, 7, 3))
        for y in range(ROOM_Y + 42, ROOM_Y + ROOM_H - WALL_SIZE, 70):
            pygame.draw.line(SCREEN, GRID, (inner.left, y), (inner.right, y), 2)
        # Небольшие напольные маркировки и заклёпки.
        for x in (ROOM_X + 58, ROOM_X + ROOM_W - 76):
            for y in (ROOM_Y + 64, ROOM_Y + ROOM_H - 78):
                pygame.draw.rect(SCREEN, (104, 81, 42), (x, y, 18, 5))
                pygame.draw.rect(SCREEN, (172, 128, 54), (x, y, 5, 5))
        for x in range(ROOM_X + 12, ROOM_X + ROOM_W - 12, 28):
            pygame.draw.rect(SCREEN, (76, 83, 92), (x, ROOM_Y + 5, 8, 4))
            pygame.draw.rect(SCREEN, (76, 83, 92), (x, ROOM_Y + ROOM_H - 9, 8, 4))
        # Аварийные лампы по стенам слегка мерцают, но не влияют на игровой процесс.
        tick = pygame.time.get_ticks()
        flicker = 1 if (tick // 170) % 7 != 0 else 0
        for lx, ly in ((ROOM_X + 105, ROOM_Y + 8),
                       (ROOM_X + ROOM_W - 112, ROOM_Y + 8),
                       (ROOM_X + 105, ROOM_Y + ROOM_H - 14),
                       (ROOM_X + ROOM_W - 112, ROOM_Y + ROOM_H - 14)):
            # Мягкое красное свечение аварийной лампы на стене.
            glow = pygame.Surface((64, 40), pygame.SRCALPHA)
            glow_alpha = 32 if flicker else 12
            pygame.draw.ellipse(glow, (255, 42, 35, glow_alpha), (0, 0, 64, 40))
            SCREEN.blit(glow, (lx - 23, ly - 17))
            pygame.draw.rect(SCREEN, (62, 18, 22), (lx - 5, ly - 3, 28, 12))
            lamp_color = (235, 52, 43) if flicker else (105, 28, 30)
            pygame.draw.rect(SCREEN, lamp_color, (lx, ly, 18, 6))
            pygame.draw.rect(SCREEN, (255, 125, 78) if flicker else (125, 45, 42),
                             (lx + 3, ly + 1, 5, 2))

        # Дополнительные детали пола: потёртости, сервисные люки и предупреждающие полосы.
        # Координаты фиксированы — рисунок не мерцает при каждом кадре.
        for i in range(18):
            sx = ROOM_X + 48 + (i * 97) % (ROOM_W - 96)
            sy = ROOM_Y + 58 + (i * 137) % (ROOM_H - 116)
            pygame.draw.line(SCREEN, (29, 34, 40), (sx, sy), (sx + 8 + i % 13, sy), 1)
            if i % 3 == 0:
                pygame.draw.rect(SCREEN, (32, 39, 46), (sx + 15, sy + 7, 3, 3))
        # Технические люки с болтами добавляют глубину индустриальному полу.
        for hx, hy in ((ROOM_X+150, ROOM_Y+150), (ROOM_X+ROOM_W-155, ROOM_Y+150),
                       (ROOM_X+150, ROOM_Y+ROOM_H-150), (ROOM_X+ROOM_W-155, ROOM_Y+ROOM_H-150)):
            hatch = pygame.Rect(hx-22, hy-15, 44, 30)
            pygame.draw.rect(SCREEN, (10, 13, 18), hatch.move(2, 3), border_radius=3)
            pygame.draw.rect(SCREEN, (31, 39, 47), hatch, border_radius=3)
            pygame.draw.rect(SCREEN, (67, 77, 86), hatch, 2, border_radius=3)
            pygame.draw.line(SCREEN, (17, 22, 28), (hx-13, hy), (hx+13, hy), 3)
            for bx in (hx-16, hx+16):
                pygame.draw.circle(SCREEN, (113, 122, 128), (bx, hy-9), 2)
                pygame.draw.circle(SCREEN, (113, 122, 128), (bx, hy+9), 2)
        # Жёлто-чёрная маркировка опасной зоны у части стен.
        for i in range(7):
            ax = ROOM_X + ROOM_W//2 - 42 + i*12
            ay = ROOM_Y + WALL_SIZE + 5
            if i % 2 == 0:
                pygame.draw.line(SCREEN, (137, 94, 34), (ax, ay), (ax+7, ay+8), 3)
        # Тонкая внутренняя окантовка стен и светлые кромки металлических панелей.
        pygame.draw.rect(SCREEN, (82, 91, 101),
                         (ROOM_X+3, ROOM_Y+3, ROOM_W-6, ROOM_H-6), 2)
        pygame.draw.line(SCREEN, (35, 42, 51),
                         (inner.left+2, inner.top+2), (inner.right-2, inner.top+2), 2)
        pygame.draw.line(SCREEN, (35, 42, 51),
                         (inner.left+2, inner.top+2), (inner.left+2, inner.bottom-2), 2)

        # Укрытия, ящики и обломки делают комнаты визуально разными.
        for i, obstacle in enumerate(self.obstacles):
            base = (76, 83, 92) if i % 2 == 0 else (93, 75, 57)
            pygame.draw.rect(SCREEN, (12, 14, 18), obstacle.move(4, 5), border_radius=5)
            pygame.draw.rect(SCREEN, base, obstacle, border_radius=5)
            pygame.draw.rect(SCREEN, (145, 151, 158), obstacle, 2, border_radius=5)
            # Полосы на поверхности напоминают металл и потёртые ящики.
            if obstacle.width > obstacle.height:
                pygame.draw.line(SCREEN, (48, 54, 62),
                                 (obstacle.left + 8, obstacle.centery),
                                 (obstacle.right - 8, obstacle.centery), 3)
            else:
                pygame.draw.line(SCREEN, (48, 54, 62),
                                 (obstacle.centerx, obstacle.top + 7),
                                 (obstacle.centerx, obstacle.bottom - 7), 3)

        # Четыре двери — как в классическом room-based roguelike.
        door_specs = {
            "top": (ROOM_X + ROOM_W//2 - 48, ROOM_Y + WALL_SIZE - 2, 96, 48),
            "bottom": (ROOM_X + ROOM_W//2 - 48, ROOM_Y + ROOM_H - WALL_SIZE - 46, 96, 48),
            "left": (ROOM_X + WALL_SIZE - 2, ROOM_Y + ROOM_H//2 - 48, 48, 96),
            "right": (ROOM_X + ROOM_W - WALL_SIZE - 46, ROOM_Y + ROOM_H//2 - 48, 48, 96),
        }
        # Рисуем только двери, за которыми действительно есть соседняя комната.
        # Отсутствующие проходы выглядят как сплошная стена, даже пока комната не зачищена.
        available_sides = self.neighbors_of(self.current_cell)
        for side, rect_data in door_specs.items():
            if side not in available_sides:
                continue
            rect = pygame.Rect(*rect_data)
            if self.door_open:
                pygame.draw.rect(SCREEN, CYAN, rect, border_radius=7)
                pygame.draw.rect(SCREEN, WHITE, rect, 3, border_radius=7)
                # Внутреннее свечение.
                inner = rect.inflate(-12, -12)
                pygame.draw.rect(SCREEN, (35, 80, 92), inner, border_radius=5)
            else:
                pygame.draw.rect(SCREEN, (48, 52, 60), rect, border_radius=5)
                pygame.draw.rect(SCREEN, (90, 94, 105), rect, 2, border_radius=5)

        if self.door_open:
            text(SCREEN, "ДВЕРИ ОТКРЫТЫ", SMALL, CYAN, ROOM_X + ROOM_W//2, ROOM_Y + ROOM_H + 12, True)

        # Отдельная дверь-портал на следующий уровень, не заменяющая обычные двери карты.
        if self.current_cell == self.boss_cell:
            portal = self.level_exit_rect
            portal_color = (50, 225, 245) if self.level_exit_open else (72, 77, 87)
            pygame.draw.rect(SCREEN, (12, 15, 22), portal.move(4, 5), border_radius=12)
            pygame.draw.rect(SCREEN, portal_color, portal, border_radius=12)
            pygame.draw.rect(SCREEN, WHITE if self.level_exit_open else (125, 130, 140), portal, 3, border_radius=12)
            inner_portal = portal.inflate(-18, -16)
            pygame.draw.rect(SCREEN, (20, 75, 95) if self.level_exit_open else (43, 46, 53), inner_portal, border_radius=8)
            if self.level_exit_open:
                text(SCREEN, "ВЫХОД", SMALL, WHITE, portal.centerx, portal.centery, True)
                text(SCREEN, "ВОЙДИ В ПОРТАЛ", SMALL, CYAN, portal.centerx, portal.bottom + 14, True)
            else:
                text(SCREEN, "ВЫХОД ЗАКРЫТ", SMALL, LIGHT, portal.centerx, portal.bottom + 14, True)

        if self.transition_timer > 0:
            alpha = int(255 * max(0, min(1, self.transition_timer / .24)))
            fade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fade.fill((0, 0, 0, alpha))
            SCREEN.blit(fade, (0, 0))

    def draw_lighting_overlay(self):
        """Псевдоосвещение без шейдеров: тёмная маска с мягкой зоной видимости вокруг солдата."""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((2, 4, 9, 158))
        px, py = int(self.player.x), int(self.player.y)
        # Несколько ступеней создают ретро-эффект фонаря без дорогих эффектов.
        pygame.draw.circle(overlay, (2, 4, 9, 118), (px, py), 185)
        pygame.draw.circle(overlay, (2, 4, 9, 72), (px, py), 135)
        pygame.draw.circle(overlay, (2, 4, 9, 28), (px, py), 82)
        pygame.draw.rect(overlay, (2, 4, 9, 45),
                         (ROOM_X, ROOM_Y, ROOM_W, WALL_SIZE))
        pygame.draw.rect(overlay, (2, 4, 9, 45),
                         (ROOM_X, ROOM_Y + ROOM_H - WALL_SIZE, ROOM_W, WALL_SIZE))
        SCREEN.blit(overlay, (0, 0))
        # Не рисуем направленный луч линиями: при пиксельной графике он выглядит
        # как длинный прямоугольный столбик перед солдатом. Атмосферу темноты
        # создают концентрические зоны видимости вокруг персонажа.

    def draw_hud(self):
        pygame.draw.rect(SCREEN, (12, 14, 19),
                         (0, 0, WIDTH, 72))

        text(SCREEN,
             f"HP {self.player.hp}/{self.player.max_hp}",
             FONT, WHITE, 18, 10)

        pygame.draw.rect(SCREEN, BLACK, (18, 42, 180, 12))
        hp_ratio = max(0.0, min(1.0, self.player.hp / max(1, self.player.max_hp)))
        hp_color = RED if hp_ratio <= 0.25 else ORANGE if hp_ratio <= 0.5 else GREEN
        pygame.draw.rect(
            SCREEN, hp_color,
            (18, 42, int(180 * hp_ratio), 12)
        )
        # Критическое здоровье заметно даже в тёмной комнате.
        if hp_ratio <= 0.25:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 115.0)
            warning_color = (255, int(65 + 65 * pulse), int(55 + 25 * pulse))
            text(SCREEN, "КРИТИЧЕСКОЕ ЗДОРОВЬЕ!", SMALL, warning_color, 18, 57)
            if pulse > 0.72:
                border = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                pygame.draw.rect(border, (235, 25, 30, 48), (0, 0, WIDTH, HEIGHT), 8)
                SCREEN.blit(border, (0, 0))

        text(SCREEN,
             f"SCRAP: {self.player.scrap}",
             FONT, YELLOW, 230, 10)
        text(SCREEN, f"KILLS {self.player.kills}",
             SMALL, (166, 176, 184), 230, 38)
        # Индикатор цели показывает прогресс к 30 запчастям для финального босса.
        scrap_goal_ratio = max(0.0, min(1.0, self.player.scrap / 30.0))
        pygame.draw.rect(SCREEN, BLACK, (230, 59, 120, 7), border_radius=2)
        if scrap_goal_ratio > 0:
            goal_color = GREEN if self.player.scrap >= 30 else YELLOW
            pygame.draw.rect(SCREEN, goal_color,
                             (230, 59, int(120 * scrap_goal_ratio), 7), border_radius=2)
        pygame.draw.rect(SCREEN, WALL, (230, 59, 120, 7), 1, border_radius=2)
        text(SCREEN, "ЦЕЛЬ 30", TINY,
             GREEN if self.player.scrap >= 30 else LIGHT, 358, 55)

        text(SCREEN,
             f"DMG {self.player.damage}",
             SMALL, WHITE, 425, 8)
        text(SCREEN,
             f"SPD {self.player.speed}",
             SMALL, WHITE, 425, 30)

        text(SCREEN,
             f"x{self.player.multishot}  ARM {self.player.armor}",
             SMALL, WHITE, 555, 8)
        text(SCREEN,
             f"CRIT {int(self.player.crit_chance*100)}%",
             SMALL, WHITE, 555, 30)

        text(SCREEN,
             f"{self.level}/10  ROOM {self.room}/{self.level_room_count}",
             FONT, WHITE, 740, 10)
        text(SCREEN, self.room_type.upper(), SMALL, CYAN, 740, 38)
        # Индикатор активного элемента и доступной синергии.
        if self.player.electric_rounds:
            element_label, element_color = "ЭЛЕКТРОДУГИ", CYAN
            synergy = "УСИЛЕННАЯ ДУГА" if self.player.crit_chance >= 0.20 else "ДУГА + КРИТ 20%"
        elif self.player.incendiary_rounds:
            element_label, element_color = "ЗАЖИГАТЕЛЬНЫЕ", ORANGE
            synergy = "ИНФЕРНО АКТИВНО" if self.player.damage >= 6 else "ИНФЕРНО: УРОН 6"
        elif self.player.piercing_rounds:
            element_label, element_color = "ПРОБОЙНИК", PURPLE
            extra = min(2, max(0, self.player.multishot - 1))
            synergy = f"ПРОБИТИЕ +{extra}" if extra else "МУЛЬТИВЫСТРЕЛ x2"
        else:
            element_label, element_color = "ОБЫЧНЫЕ ПУЛИ", LIGHT
            synergy = "НЕТ ЭЛЕМЕНТА"
        text(SCREEN, element_label, TINY, element_color, 425, 52)
        text(SCREEN, synergy, TINY, element_color, 555, 52)
        weapon = WEAPONS[self.player.weapon_index]
        text(SCREEN, f"{weapon['name']}  [1/2/3/4]", SMALL, weapon["color"], 885, 38, True)

        grenade_label = "ГОТОВА" if self.player.grenade_timer <= 0 else f"{self.player.grenade_timer:.1f}с"
        shield_label = "ГОТОВ" if self.player.shield_ready else f"{self.player.shield_cooldown_timer:.1f}с"
        shield_state = f"АКТИВЕН {self.player.shield_timer:.1f}с" if self.player.shield_timer > 0 else shield_label
        text(SCREEN, f"SHIFT РЫВОК | G ГРАНАТА: {grenade_label} | Q ЩИТ: {shield_state}",
             SMALL, CYAN if self.player.shield_timer > 0 else LIGHT, 18, HEIGHT-25)

    def draw_minimap(self):
        """Миникарта уровня: комнаты и связи между ними."""
        if not self.map_cells:
            return

        panel = pygame.Rect(885, 78, 200, 194)
        pygame.draw.rect(SCREEN, (10, 13, 18), panel, border_radius=10)
        pygame.draw.rect(SCREEN, WALL, panel, 2, border_radius=10)
        text(SCREEN, "КАРТА", SMALL, LIGHT, panel.centerx, panel.y + 14, True)

        min_x = min(c[0] for c in self.map_cells)
        max_x = max(c[0] for c in self.map_cells)
        min_y = min(c[1] for c in self.map_cells)
        max_y = max(c[1] for c in self.map_cells)
        span_x = max(1, max_x - min_x)
        span_y = max(1, max_y - min_y)
        scale = min(150 / span_x if span_x else 150, 110 / span_y if span_y else 110)
        scale = min(scale, 42)
        cx, cy = panel.centerx, panel.y + 98

        def pos(cell):
            return (int(cx + (cell[0] - (min_x + max_x)/2) * scale),
                    int(cy + (cell[1] - (min_y + max_y)/2) * scale))

        # Связи между комнатами.
        for cell in self.map_cells:
            x, y = pos(cell)
            for target in self.neighbors_of(cell).values():
                if self.map_cells.index(cell) < self.map_cells.index(target):
                    tx, ty = pos(target)
                    pygame.draw.line(SCREEN, (58, 64, 76), (x, y), (tx, ty), 3)

        for cell in self.map_cells:
            x, y = pos(cell)
            if cell == self.current_cell:
                color = YELLOW
                radius = 7
            elif cell == self.boss_cell and cell not in self.cleared_cells:
                color = RED
                radius = 6
            elif cell in self.cleared_cells:
                # Зелёная точка означает, что комната уже зачищена.
                color = GREEN
                radius = 5
            elif cell in self.visited_cells:
                color = CYAN
                radius = 5
            else:
                color = (75, 80, 90)
                radius = 4
            pygame.draw.circle(SCREEN, color, (x, y), radius)
            if cell == self.boss_cell:
                pygame.draw.circle(SCREEN, WHITE, (x, y), radius + 2, 1)

        # Легенда миникарты: помогает различать состояние комнат без догадок.
        legend_y = panel.bottom - 15
        legend = [((75, 80, 90), "Новая"), (CYAN, "Посещена"), (GREEN, "Зачищена"), (RED, "Босс")]
        legend_x = panel.x + 9
        for dot_color, label in legend:
            pygame.draw.circle(SCREEN, dot_color, (legend_x + 4, legend_y), 3)
            text(SCREEN, label, TINY, LIGHT, legend_x + 11, legend_y - 6)
            legend_x += 48 if label != "Посещена" else 56

    def draw_playing(self):
        self.draw_room_background()

        for trap in self.traps:
            trap.draw(SCREEN)
        for crate in self.crates:
            crate.draw(SCREEN)

        for s in self.scraps:
            s.draw(SCREEN)

        for m in self.medkits:
            m.draw(SCREEN)

        for b in self.bullets:
            b.draw(SCREEN)

        for e in self.enemies:
            e.draw(SCREEN)

        if self.boss:
            self.boss.draw(SCREEN)

        # Сначала рисуем частицы и маску освещения. Фонарный луч начинается
        # в центре игрока, поэтому персонажа обязательно рисуем ПОВЕРХ маски:
        # иначе луч перекрывает спрайт длинной серой полосой.
        for p in self.particles:
            p.draw(SCREEN)
        for effect in self.shockwaves:
            effect.draw(SCREEN)

        self.draw_lighting_overlay()

        # Спрайт и щит находятся на верхнем слое: свет освещает пол,
        # но не рисуется поверх тела солдата.
        self.player.draw(SCREEN)
        if self.player.shield_timer > 0:
            pulse = int(3 + 2 * math.sin(pygame.time.get_ticks() / 90))
            pygame.draw.circle(SCREEN, CYAN,
                               (int(self.player.x), int(self.player.y)),
                               self.player.radius + 9 + pulse, 3)

        self.draw_hud()
        self.draw_minimap()
        # Цифры урона и подписи наград рисуем поверх маски освещения.
        for label in self.damage_texts:
            label.draw(SCREEN)

        # Экранная вспышка показывает, что игрок действительно получил урон.
        # HUD и текст остаются читаемыми благодаря небольшой прозрачности.
        if self.hurt_flash_timer > 0:
            alpha = int(105 * (self.hurt_flash_timer / 0.22))
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((220, 25, 35, alpha))
            SCREEN.blit(flash, (0, 0))

        # Постоянный, но мягкий сигнал опасности при низком здоровье.
        # Он не закрывает центр экрана, поэтому игрок продолжает видеть бой.
        if self.player.max_hp > 0:
            hp_ratio = max(0.0, min(1.0, self.player.hp / self.player.max_hp))
            if 0 < hp_ratio <= 0.25 and self.state in ("playing", "final_boss"):
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 170.0)
                alpha = int(22 + pulse * 28)
                edge = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                edge_color = (235, 28, 35, alpha)
                # Несколько тонких слоёв создают пиксельную рамку по краям.
                for thickness in (8, 16, 24):
                    layer_alpha = max(8, alpha - thickness // 2)
                    pygame.draw.rect(
                        edge, (edge_color[0], edge_color[1], edge_color[2], layer_alpha),
                        (thickness, thickness, WIDTH - thickness * 2, HEIGHT - thickness * 2),
                        width=3
                    )
                SCREEN.blit(edge, (0, 0))
                if hp_ratio <= 0.12:
                    warning = SMALL.render("КРИТИЧЕСКОЕ ЗДОРОВЬЕ", True, (255, 95, 85))
                    warning.set_alpha(int(150 + pulse * 105))
                    SCREEN.blit(warning, warning.get_rect(center=(WIDTH // 2, 54)))

        if self.message_timer > 0:
            text(SCREEN, self.message,
                 FONT, YELLOW,
                 WIDTH//2, HEIGHT-28, True)

    def draw_final_boss(self):
        SCREEN.fill((6, 8, 12))

        pygame.draw.rect(
            SCREEN, ROOM,
            (ROOM_X, ROOM_Y, ROOM_W, ROOM_H)
        )
        pygame.draw.rect(
            SCREEN, WALL,
            (ROOM_X, ROOM_Y, ROOM_W, ROOM_H),
            WALL_SIZE
        )

        boss = self.final_boss

        # Красный крест показывает линии будущего залпа, пока позиция игрока ещё зафиксирована.
        if boss.get("cross_warning", 0) > 0:
            tx, ty = int(boss["cross_target_x"]), int(boss["cross_target_y"])
            warning_color = (255, 235, 145) if int(boss["cross_warning"] * 18) % 2 else CYAN
            left, right = ROOM_X + WALL_SIZE + 6, ROOM_X + ROOM_W - WALL_SIZE - 6
            top, bottom = ROOM_Y + WALL_SIZE + 6, ROOM_Y + ROOM_H - WALL_SIZE - 6
            pygame.draw.line(SCREEN, (70, 165, 175), (left, ty - 16), (right, ty - 16), 1)
            pygame.draw.line(SCREEN, (70, 165, 175), (left, ty + 16), (right, ty + 16), 1)
            pygame.draw.line(SCREEN, (70, 165, 175), (tx - 16, top), (tx - 16, bottom), 1)
            pygame.draw.line(SCREEN, (70, 165, 175), (tx + 16, top), (tx + 16, bottom), 1)
            pygame.draw.line(SCREEN, warning_color, (left, ty), (right, ty), 3)
            pygame.draw.line(SCREEN, warning_color, (tx, top), (tx, bottom), 3)
            pulse = 18 + int((0.92 - boss["cross_warning"]) * 14)
            pygame.draw.circle(SCREEN, warning_color, (tx, ty), pulse, 3)
            text(SCREEN, "КРЕСТОВОЙ ЗАЛП — УЙДИ С ЛИНИЙ!", SMALL,
                 warning_color, tx, ty - 34, True)

        # Arena cover: these barriers block and absorb shots until destroyed.
        for cover in self.boss_cover:
            rect = cover["rect"]
            if cover["hp"] <= 0:
                continue
            ratio_cover = max(0.0, min(1.0, cover["hp"] / cover["max_hp"]))
            base_cover = (88, 75, 86) if cover["flash"] > 0 else (54, 63, 74)
            pygame.draw.rect(SCREEN, (8, 10, 15), rect.move(4, 5), border_radius=4)
            pygame.draw.rect(SCREEN, base_cover, rect, border_radius=4)
            pygame.draw.rect(SCREEN, CYAN if cover["flash"] > 0 else (132, 151, 164), rect, 2, border_radius=4)
            pygame.draw.line(SCREEN, (25, 31, 40),
                             (rect.left + 8, rect.centery),
                             (rect.right - 8, rect.centery), 4)
            pygame.draw.rect(SCREEN, BLACK, (rect.left, rect.top - 7, rect.width, 4))
            pygame.draw.rect(SCREEN, GREEN if ratio_cover > .5 else ORANGE,
                             (rect.left, rect.top - 7, int(rect.width * ratio_cover), 4))
            if ratio_cover < .55:
                pygame.draw.line(SCREEN, ORANGE,
                                 (rect.left + 12, rect.top + 4),
                                 (rect.left + 24, rect.bottom - 4), 2)

        # Telegraph the arena sweep as red danger zones with a cyan safe corridor.
        sweep_warning = boss.get("sweep_warning", 0.0)
        sweep_active = boss.get("sweep_active", 0.0)
        if sweep_warning > 0 or sweep_active > 0:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            left = ROOM_X + WALL_SIZE
            right = ROOM_X + ROOM_W - WALL_SIZE
            top = ROOM_Y + WALL_SIZE
            bottom = ROOM_Y + ROOM_H - WALL_SIZE
            active = sweep_active > 0
            alpha = 76 if active else (32 + int(22 * math.sin(boss["timer"] * 24)))
            danger = (225, 38, 46, alpha)
            if boss["sweep_axis"] == "vertical":
                gx = int(boss["sweep_gap_x"])
                pygame.draw.rect(overlay, danger, (left, top, max(0, gx - 66 - left), bottom-top))
                pygame.draw.rect(overlay, danger, (gx + 66, top, max(0, right - gx - 66), bottom-top))
                pygame.draw.rect(overlay, (52, 215, 223, 55 if not active else 95),
                                 (gx-66, top, 132, bottom-top))
                pygame.draw.line(overlay, (117, 250, 255, 210), (gx-66, top), (gx-66, bottom), 3)
                pygame.draw.line(overlay, (117, 250, 255, 210), (gx+66, top), (gx+66, bottom), 3)
                label_x, label_y = gx, top + 20
            else:
                gy = int(boss["sweep_gap_y"])
                pygame.draw.rect(overlay, danger, (left, top, right-left, max(0, gy - 66 - top)))
                pygame.draw.rect(overlay, danger, (left, gy + 66, right-left, max(0, bottom - gy - 66)))
                pygame.draw.rect(overlay, (52, 215, 223, 55 if not active else 95),
                                 (left, gy-66, right-left, 132))
                pygame.draw.line(overlay, (117, 250, 255, 210), (left, gy-66), (right, gy-66), 3)
                pygame.draw.line(overlay, (117, 250, 255, 210), (left, gy+66), (right, gy+66), 3)
                label_x, label_y = left + 132, gy
            SCREEN.blit(overlay, (0, 0))
            if not active:
                text(SCREEN, "БЕЗОПАСНЫЙ ПРОХОД", SMALL, CYAN,
                     label_x, label_y, True)
            else:
                text(SCREEN, "ИМПУЛЬС!", SMALL, WHITE,
                     label_x, label_y, True)

        # The final drone changes armor palette and silhouette as its reactor overloads.
        phase = boss["phase"]
        if phase == 1:
            shell_color, plate_color, spike_color = DARK_RED, RED, ORANGE
            title_name = "ОГРОМНЫЙ ДРОН — ОСНОВНОЙ РЕЖИМ"
        elif phase == 2:
            shell_color, plate_color, spike_color = (44, 24, 65), PURPLE, CYAN
            title_name = "ОГРОМНЫЙ ДРОН — РЕАКТОР"
        else:
            shell_color, plate_color, spike_color = (16, 39, 48), CYAN, (190, 64, 220)
            title_name = "ОГРОМНЫЙ ДРОН — ПЕРЕГРУЗКА"
        pygame.draw.circle(SCREEN, shell_color,
                           (int(boss["x"]), int(boss["y"])), 90)
        pygame.draw.circle(SCREEN, plate_color,
                           (int(boss["x"]), int(boss["y"])), 72)
        pygame.draw.circle(SCREEN, BLACK,
                           (int(boss["x"]), int(boss["y"])), 72, 6)
        if phase >= 2:
            pygame.draw.circle(SCREEN, spike_color,
                               (int(boss["x"]), int(boss["y"])), 98, 4)
        if phase >= 3:
            pygame.draw.circle(SCREEN, PURPLE,
                               (int(boss["x"]), int(boss["y"])), 108, 2)

        for angle in range(0, 360, 30 if phase == 1 else 24 if phase == 2 else 18):
            a = math.radians(angle + int(boss["timer"] * (12 if phase == 1 else 22 if phase == 2 else 34)))
            x1 = boss["x"] + math.cos(a)*60
            y1 = boss["y"] + math.sin(a)*60
            x2 = boss["x"] + math.cos(a)*(125 if phase < 3 else 139)
            y2 = boss["y"] + math.sin(a)*(125 if phase < 3 else 139)
            pygame.draw.line(
                SCREEN, spike_color,
                (int(x1), int(y1)),
                (int(x2), int(y2)), 12 if phase == 1 else 10 if phase == 2 else 8
            )

        # Дополнительная броня финального босса: сегментированные пластины, двигатели и кабели.
        # Геометрия меняет цвет и интенсивность вместе с фазой перегрузки реактора.
        bx, by = int(boss["x"]), int(boss["y"])
        glow_layer = pygame.Surface((300, 300), pygame.SRCALPHA)
        glow_alpha = 24 + int(18 * (0.5 + 0.5 * math.sin(boss["timer"] * 5)))
        pygame.draw.circle(glow_layer, (*spike_color, glow_alpha), (150, 150), 132)
        pygame.draw.circle(glow_layer, (*plate_color, glow_alpha), (150, 150), 92)
        SCREEN.blit(glow_layer, (bx-150, by-150))
        # Восемь бронированных лепестков вокруг реактора.
        for i in range(8):
            a = math.radians(i*45 + boss["timer"]*(18 if phase == 1 else 28 if phase == 2 else 38))
            ca, sa = math.cos(a), math.sin(a)
            p1 = (int(bx+ca*66-sa*13), int(by+sa*66+ca*13))
            p2 = (int(bx+ca*91), int(by+sa*91))
            p3 = (int(bx+ca*66+sa*13), int(by+sa*66-ca*13))
            pygame.draw.polygon(SCREEN, (5, 8, 14), [p1, p2, p3])
            pygame.draw.polygon(SCREEN, plate_color, [p1, p2, p3], 3)
            pygame.draw.circle(SCREEN, spike_color, p2, 4 + (phase == 3))
        # Радиальные силовые кабели и крепёжные узлы.
        for i in range(4):
            a = math.radians(45 + i*90)
            sx, sy = int(bx+math.cos(a)*48), int(by+math.sin(a)*48)
            ex, ey = int(bx+math.cos(a)*76), int(by+math.sin(a)*76)
            pygame.draw.line(SCREEN, (5, 7, 12), (sx, sy), (ex, ey), 9)
            pygame.draw.line(SCREEN, spike_color, (sx, sy), (ex, ey), 3)
            pygame.draw.circle(SCREEN, (185, 195, 205), (ex, ey), 5, 2)
        # Пульсирующие вентиляционные прорези на корпусе.
        for side in (-1, 1):
            for row in range(3):
                yy = by - 25 + row*25
                xx = bx + side*(48 + (row % 2)*4)
                pygame.draw.line(SCREEN, (5, 8, 13), (xx-7, yy), (xx+7, yy), 7)
                pygame.draw.line(SCREEN, spike_color, (xx-5, yy), (xx+5, yy), 2)
        # В фазе перегрузки реактор выбрасывает яркие энергетические дуги.
        if phase >= 2:
            for i in range(4):
                a = boss["timer"]*1.7 + i*math.pi/2
                arc_rect = pygame.Rect(bx-116, by-116, 232, 232)
                start_angle = a % math.tau
                pygame.draw.arc(SCREEN, spike_color, arc_rect, start_angle, start_angle+0.48, 4)

        # Core color signals both phase and whether the player has a damage window.
        core_color = CYAN if boss["core_open"] > 0 else YELLOW if phase == 1 else PURPLE if phase == 2 else RED
        pygame.draw.circle(
            SCREEN, core_color,
            (int(boss["x"]), int(boss["y"])), 20
        )
        if boss["phase"] >= 2 and boss["core_open"] > 0:
            pygame.draw.circle(SCREEN, WHITE,
                               (int(boss["x"]), int(boss["y"])), 31, 4)
        if boss.get("ring_warning", 0) > 0:
            pulse = int(105 + 35 * math.sin(boss["timer"] * 24))
            ring_color = (255, max(70, pulse), 35)
            pygame.draw.circle(
                SCREEN, ring_color,
                (int(boss["x"]), int(boss["y"])),
                int(105 + (0.7 - boss["ring_warning"]) * 70), 4
            )
            text(SCREEN, "ЗАЛП ПО КРУГУ — ОТОЙДИ!", SMALL, ring_color,
                 int(boss["x"]), int(boss["y"])-112, True)

        if boss["warning"] > 0:
            pygame.draw.circle(SCREEN, ORANGE,
                               (int(boss["dash_x"]), int(boss["dash_y"])), 32, 4)
            text(SCREEN, "УКЛОНЯЙСЯ!", SMALL, ORANGE,
                 int(boss["dash_x"]), int(boss["dash_y"])-45, True)

        if boss["shot_warning"] > 0:
            # Линия показывает направление будущего веера; мерцает перед выстрелом.
            line_color = WHITE if int(boss["shot_warning"] * 24) % 2 else ORANGE
            pygame.draw.line(
                SCREEN, line_color,
                (int(boss["x"]), int(boss["y"])),
                (int(boss["shot_target_x"]), int(boss["shot_target_y"])), 3
            )
            pygame.draw.circle(
                SCREEN, line_color,
                (int(boss["shot_target_x"]), int(boss["shot_target_y"])), 18, 3
            )
            text(SCREEN, "АТАКА!", SMALL, ORANGE,
                 int(boss["shot_target_x"]), int(boss["shot_target_y"])-28, True)

        for b in self.bullets:
            b.draw(SCREEN)

        for e in self.enemies:
            e.draw(SCREEN)

        for s in self.scraps:
            s.draw(SCREEN)

        self.player.draw(SCREEN)
        if self.player.shield_timer > 0:
            pulse = int(3 + 2 * math.sin(pygame.time.get_ticks() / 90))
            pygame.draw.circle(SCREEN, CYAN,
                               (int(self.player.x), int(self.player.y)),
                               self.player.radius + 9 + pulse, 3)

        for p in self.particles:
            p.draw(SCREEN)
        for effect in self.shockwaves:
            effect.draw(SCREEN)
        for label in self.damage_texts:
            label.draw(SCREEN)

        # Boss bar.
        text(SCREEN, title_name,
             MEDIUM, WHITE, WIDTH//2, 18, True)

        pygame.draw.rect(SCREEN, BLACK,
                         (270, 48, 560, 20))
        phase_bar_color = RED if boss["phase"] == 1 else PURPLE if boss["phase"] == 2 else CYAN
        pygame.draw.rect(
            SCREEN, phase_bar_color,
            (270, 48,
             int(560*max(0,boss["hp"])/boss["max_hp"]), 20)
        )

        text(SCREEN,
             f"ЗАПЧАСТИ: {self.player.scrap}/30",
             FONT, YELLOW, 20, 20)
        scrap_goal_ratio = max(0.0, min(1.0, self.player.scrap / 30.0))
        pygame.draw.rect(SCREEN, BLACK, (20, 49, 170, 8), border_radius=2)
        if scrap_goal_ratio > 0:
            goal_color = GREEN if self.player.scrap >= 30 else YELLOW
            pygame.draw.rect(SCREEN, goal_color,
                             (20, 49, int(170 * scrap_goal_ratio), 8), border_radius=2)
        pygame.draw.rect(SCREEN, WALL, (20, 49, 170, 8), 1, border_radius=2)

        phase_label_color = CYAN if boss.get("phase_recovery", 0) > 0 else ORANGE
        text(SCREEN,
             f"ФАЗА {boss['phase']}",
             FONT, phase_label_color, 900, 20)
        if boss.get("phase_recovery", 0) > 0:
            text(SCREEN, "ОКНО АТАКИ БОССА", TINY, CYAN, 900, 40)

        if self.message_timer > 0:
            text(SCREEN, self.message,
                 FONT, YELLOW,
                 WIDTH//2, HEIGHT-28, True)

    # ---------------- MENUS ----------------

    def draw_menu(self):
        SCREEN.fill((5, 7, 11))
        # Ретро-фон главного меню: панели бункера и красные сигнальные линии.
        for y in range(35, HEIGHT, 42):
            pygame.draw.line(SCREEN, (15, 21, 28), (80, y), (WIDTH-80, y), 2)
        pygame.draw.rect(SCREEN, (28, 17, 21), (210, 104, 680, 90))
        pygame.draw.rect(SCREEN, (132, 35, 35), (210, 104, 680, 5))
        pygame.draw.rect(SCREEN, (132, 35, 35), (210, 189, 680, 5))
        text(SCREEN, "DRONE HUNTER",
             BIG, WHITE, WIDTH//2, 145, True)

        text(SCREEN,
             "ROGUELIKE • SURVIVE • UPGRADE • DESTROY",
             SMALL, LIGHT, WIDTH//2, 200, True)

        buttons = [
            ("ENTER", "НОВАЯ ИГРА"),
            ("L", "ЗАГРУЗИТЬ СОХРАНЕНИЕ"),
            ("A", "ДОСТИЖЕНИЯ"),
            ("ESC", "ВЫХОД"),
        ]

        y = 290
        for key, label in buttons:
            pygame.draw.rect(
                SCREEN, (28, 33, 42),
                (300, y, 500, 60)
            )
            pygame.draw.rect(
                SCREEN, WALL,
                (300, y, 500, 60), 2
            )
            text(SCREEN, f"[{key}]  {label}",
                 FONT, WHITE, WIDTH//2, y+30, True)
            y += 75

        text(SCREEN,
             "WASD — движение   •   СТРЕЛКИ — стрельба   •   SHIFT — рывок",
             SMALL, LIGHT, WIDTH//2, 585, True)
        text(SCREEN,
             "1/2/3/4 — оружие   •   После зачистки войди в любую дверь   •   ESC — меню",
             SMALL, LIGHT, WIDTH//2, 610, True)

        profile_line = (f"ПИЛОТ: ЗАБЕГИ {self.profile['runs']}  •  ПОБЕДЫ {self.profile['wins']}  •  ВСЕГО УБИЙСТВ {self.profile['total_kills']}  •  ЛУЧШИЙ УРОВЕНЬ {self.profile['best_level']}")
        text(SCREEN, profile_line, SMALL, CYAN, WIDTH//2, 650, True)
        text(SCREEN, "v5.37 • RETRO 16-BIT",
             SMALL, (126, 53, 53), WIDTH-115, HEIGHT-25, True)

    def draw_achievements(self):
        SCREEN.fill((5, 7, 11))
        text(SCREEN, "АРХИВ ДОСТИЖЕНИЙ", BIG, WHITE, WIDTH//2, 90, True)
        text(SCREEN, "Постоянные цели пилота — прогресс сохраняется в pilot_profile.json", SMALL, LIGHT, WIDTH//2, 145, True)
        unlocked = set(self.profile.get("unlocked", []))
        for i, (achievement_id, title, description, _condition) in enumerate(ACHIEVEMENTS):
            y = 205 + i * 92
            color = CYAN if achievement_id in unlocked else (95, 100, 110)
            pygame.draw.rect(SCREEN, (24, 30, 39), (210, y, 680, 70), border_radius=7)
            pygame.draw.rect(SCREEN, color, (210, y, 680, 70), 2, border_radius=7)
            status = "ОТКРЫТО" if achievement_id in unlocked else "ЗАКРЫТО"
            text(SCREEN, f"{status}  •  {title}", FONT, color, 235, y+20)
            text(SCREEN, description, SMALL, LIGHT, 235, y+47)
        text(SCREEN, "ESC / A — вернуться в меню", FONT, YELLOW, WIDTH//2, 610, True)

    def draw_map(self):
        # Старый экран выбора маршрута удалён. Карта теперь отображается прямо в игре.
        self.draw_playing()

    def draw_shop(self):
        SCREEN.fill(BLACK)

        text(SCREEN, "ПОЛЕВОЙ МАГАЗИН", BIG, WHITE, WIDTH//2, 75, True)
        text(SCREEN, f"ЗАПЧАСТИ: {self.player.scrap}", MEDIUM, YELLOW, WIDTH//2, 125, True)
        text(SCREEN, "1–6 — купить предмет   •   Стрелки + ENTER — выбрать и купить", SMALL, LIGHT, WIDTH//2, 165, True)

        for i, option in enumerate(self.shop_options):
            name, kind, cost, description = option
            col = i % 3
            row = i // 3
            x = 70 + col * 330
            y = 215 + row * 170
            selected = i == self.shop_selected
            border = YELLOW if selected else WALL
            affordable = self.player.scrap >= cost
            title_color = WHITE if affordable else (120, 120, 120)

            pygame.draw.rect(SCREEN, (25, 29, 37), (x, y, 290, 135), border_radius=10)
            pygame.draw.rect(SCREEN, border, (x, y, 290, 135), 3, border_radius=10)
            text(SCREEN, str(i+1), BIG, YELLOW if selected else LIGHT, x+25, y+30, True)
            text(SCREEN, name, FONT, title_color, x+145, y+32, True)
            text(SCREEN, description, SMALL, LIGHT, x+145, y+68, True)
            text(SCREEN, f"Цена: {cost}", SMALL, YELLOW if affordable else RED, x+145, y+105, True)

        # Отдельные кнопки для покупки и выхода из магазина.
        pygame.draw.rect(SCREEN, (36, 75, 88), self.shop_buy_button, border_radius=9)
        pygame.draw.rect(SCREEN, CYAN, self.shop_buy_button, 2, border_radius=9)
        text(SCREEN, "КУПИТЬ ВЫБРАННОЕ", FONT, WHITE, self.shop_buy_button.centerx, self.shop_buy_button.centery, True)

        pygame.draw.rect(SCREEN, (43, 76, 48), self.shop_leave_button, border_radius=9)
        pygame.draw.rect(SCREEN, GREEN, self.shop_leave_button, 2, border_radius=9)
        text(SCREEN, "ВЫЙТИ И ПРОДОЛЖИТЬ", FONT, WHITE, self.shop_leave_button.centerx, self.shop_leave_button.centery, True)
        text(SCREEN, "Можно также нажать E, чтобы выйти из магазина", SMALL, LIGHT, WIDTH//2, 630, True)

    def draw_upgrade(self):
        SCREEN.fill(BLACK)

        text(SCREEN, "ВЫБЕРИ УЛУЧШЕНИЕ",
             BIG, WHITE, WIDTH//2, 100, True)

        text(SCREEN,
             "1 / 2 / 3 или стрелки + ENTER",
             SMALL, LIGHT, WIDTH//2, 150, True)

        for i, option in enumerate(self.upgrade_options):
            name, kind, description = option
            x = 80 + i*330
            y = 230

            selected = i == self.upgrade_selected
            border = YELLOW if selected else WALL

            pygame.draw.rect(
                SCREEN, (25, 29, 37),
                (x, y, 290, 250),
                border_radius=10
            )
            pygame.draw.rect(
                SCREEN, border,
                (x, y, 290, 250), 4,
                border_radius=10
            )

            text(SCREEN, str(i+1),
                 BIG, YELLOW, x+145, y+55, True)

            text(SCREEN, name,
                 MEDIUM, WHITE, x+145, y+115, True)

            text(SCREEN, description,
                 SMALL, LIGHT, x+145, y+165, True)

        text(SCREEN,
             f"Текущий урон: {self.player.damage}   "
             f"HP: {self.player.max_hp}   "
             f"Скорость: {self.player.speed}   Оружие: {WEAPONS[self.player.weapon_index]['name']}",
             SMALL, LIGHT, WIDTH//2, 550, True)

        pygame.draw.rect(SCREEN, (43, 76, 48), self.upgrade_continue_button, border_radius=9)
        pygame.draw.rect(SCREEN, GREEN, self.upgrade_continue_button, 2, border_radius=9)
        text(SCREEN, "ПРОДОЛЖИТЬ БЕЗ УЛУЧШЕНИЯ", FONT, WHITE,
             self.upgrade_continue_button.centerx, self.upgrade_continue_button.centery, True)
        text(SCREEN, "Можно нажать E или ESC", SMALL, LIGHT, WIDTH//2, 685, True)

    def draw_boss_reward(self):
        SCREEN.fill((7, 10, 17))
        # Subtle sci-fi grid in the background.
        for x in range(0, WIDTH, 40):
            pygame.draw.line(SCREEN, (17, 25, 36), (x, 0), (x, HEIGHT), 1)
        for y in range(0, HEIGHT, 40):
            pygame.draw.line(SCREEN, (17, 25, 36), (0, y), (WIDTH, y), 1)
        text(SCREEN, "БОСС УНИЧТОЖЕН", BIG, ORANGE, WIDTH//2, 72, True)
        text(SCREEN, "ВЫБЕРИ ОДНУ ИЗ ТРЁХ НАГРАД", MEDIUM, WHITE, WIDTH//2, 125, True)
        text(SCREEN, "Нажми 1 / 2 / 3 или выбери карточку мышью", SMALL, LIGHT, WIDTH//2, 165, True)
        for i, option in enumerate(self.boss_reward_options):
            name, kind, description, color = option
            x, y, w, h = 62 + i*335, 220, 300, 280
            selected = i == self.boss_reward_selected
            pygame.draw.rect(SCREEN, (21, 28, 40), (x, y, w, h), border_radius=12)
            pygame.draw.rect(SCREEN, color if selected else (65, 76, 92), (x, y, w, h), 4 if selected else 2, border_radius=12)
            pygame.draw.circle(SCREEN, color, (x+w//2, y+65), 27, 4)
            text(SCREEN, str(i+1), BIG, color, x+w//2, y+65, True)
            text(SCREEN, name, MEDIUM, WHITE, x+w//2, y+125, True)
            # Split longer reward descriptions into readable lines.
            if len(description) > 27:
                words = description.split()
                lines, line = [], ""
                for word in words:
                    if len(line) + len(word) + 1 > 27:
                        lines.append(line)
                        line = word
                    else:
                        line = (line + " " + word).strip()
                if line:
                    lines.append(line)
                for j, line in enumerate(lines[:3]):
                    text(SCREEN, line, SMALL, LIGHT, x+w//2, y+178+j*25, True)
            else:
                text(SCREEN, description, SMALL, LIGHT, x+w//2, y+185, True)
            if selected:
                text(SCREEN, "ВЫБРАНО", SMALL, color, x+w//2, y+245, True)
        text(SCREEN, "Награда применяется сразу. Выход из комнаты уже открыт.", SMALL, LIGHT, WIDTH//2, 555, True)
        pygame.draw.rect(SCREEN, (33, 57, 44), self.upgrade_continue_button, border_radius=9)
        pygame.draw.rect(SCREEN, GREEN, self.upgrade_continue_button, 2, border_radius=9)
        text(SCREEN, "ПОЛУЧИТЬ НАГРАДУ", FONT, WHITE, self.upgrade_continue_button.centerx, self.upgrade_continue_button.centery, True)

    def draw_gameover(self):
        SCREEN.fill(BLACK)

        text(SCREEN, "ТЫ ПОГИБ",
             BIG, RED, WIDTH//2, 200, True)

        text(SCREEN,
             f"Достигнут уровень: {self.level}",
             FONT, WHITE, WIDTH//2, 285, True)

        text(SCREEN,
             f"Уничтожено врагов: {self.player.kills}",
             FONT, WHITE, WIDTH//2, 325, True)

        text(SCREEN,
             "ENTER — новая игра",
             FONT, YELLOW, WIDTH//2, 405, True)

        text(SCREEN,
             "M — главное меню",
             SMALL, LIGHT, WIDTH//2, 445, True)

    def draw_victory(self):
        SCREEN.fill(BLACK)

        text(SCREEN, "МИССИЯ ВЫПОЛНЕНА",
             BIG, GREEN, WIDTH//2, 180, True)

        text(SCREEN,
             "ОГРОМНЫЙ ДРОН УНИЧТОЖЕН",
             MEDIUM, WHITE, WIDTH//2, 255, True)

        text(SCREEN,
             f"Собрано запчастей: {self.player.scrap}",
             FONT, YELLOW, WIDTH//2, 315, True)

        text(SCREEN,
             f"Уничтожено врагов: {self.player.kills}",
             FONT, WHITE, WIDTH//2, 355, True)

        text(SCREEN,
             "ENTER — начать новую игру",
             FONT, WHITE, WIDTH//2, 440, True)

        text(SCREEN,
             "ESC — выйти",
             SMALL, LIGHT, WIDTH//2, 480, True)

    def draw_pause(self):
        # Рисуем текущую игровую сцену под затемнением, не сбрасывая состояние комнаты.
        if self.paused_from == "final_boss":
            self.draw_final_boss()
        else:
            self.draw_playing()
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        SCREEN.blit(shade, (0, 0))
        pygame.draw.rect(SCREEN, WALL, (300, 175, 500, 370), border_radius=12)
        pygame.draw.rect(SCREEN, CYAN, (300, 175, 500, 370), 3, border_radius=12)
        text(SCREEN, "ПАУЗА", BIG, WHITE, WIDTH//2, 235, True)
        text(SCREEN, "ESC / P — продолжить", FONT, CYAN, WIDTH//2, 310, True)
        text(SCREEN, "F5 — сохранить игру", FONT, WHITE, WIDTH//2, 355, True)
        text(SCREEN, "M — сохранить и выйти в меню", FONT, YELLOW, WIDTH//2, 400, True)
        text(SCREEN, "Прогресс комнаты не сбрасывается", SMALL, LIGHT, WIDTH//2, 470, True)

    def draw(self):
        if self.state == "paused":
            self.draw_pause()
        elif self.state == "menu":
            self.draw_menu()
        elif self.state == "achievements":
            self.draw_achievements()
        elif self.state == "playing":
            self.draw_playing()
        elif self.state == "upgrade":
            self.draw_upgrade()
        elif self.state == "boss_reward":
            self.draw_boss_reward()
        elif self.state == "shop":
            self.draw_shop()
        elif self.state == "boss":
            self.draw_playing()
        elif self.state == "final_boss":
            self.draw_final_boss()
        elif self.state == "gameover":
            self.draw_gameover()
        elif self.state == "victory":
            self.draw_victory()

        pygame.display.flip()


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    game = Game()
    running = True

    while running:
        dt = min(CLOCK.tick(FPS)/1000.0, .05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and game.state == "upgrade":
                mx, my = event.pos
                for index in range(len(game.upgrade_options)):
                    card = pygame.Rect(80 + index * 330, 230, 290, 250)
                    if card.collidepoint(mx, my):
                        game.upgrade_selected = index
                        game.choose_upgrade()
                        break
                if game.state == "upgrade" and game.upgrade_continue_button.collidepoint(mx, my):
                    game.continue_without_upgrade()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and game.state == "boss_reward":
                mx, my = event.pos
                for index in range(len(game.boss_reward_options)):
                    card = pygame.Rect(62 + index * 335, 220, 300, 280)
                    if card.collidepoint(mx, my):
                        game.boss_reward_selected = index
                        break
                if game.state == "boss_reward" and game.upgrade_continue_button.collidepoint(mx, my):
                    game.choose_boss_reward()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and game.state == "shop":
                mx, my = event.pos
                # Clicking a card selects it; the separate button confirms purchase.
                for index in range(len(game.shop_options)):
                    col = index % 3
                    row = index // 3
                    card = pygame.Rect(70 + col * 330, 215 + row * 170, 290, 135)
                    if card.collidepoint(mx, my):
                        game.shop_selected = index
                        break
                if game.shop_buy_button.collidepoint(mx, my):
                    game.buy_shop_item()
                elif game.shop_leave_button.collidepoint(mx, my):
                    game.leave_shop()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if game.state == "menu":
                        running = False
                    elif game.state in ("playing", "boss", "final_boss"):
                        game.paused_from = game.state
                        game.state = "paused"
                    elif game.state == "paused":
                        game.state = game.paused_from
                    elif game.state == "shop":
                        game.leave_shop()
                    elif game.state == "upgrade":
                        game.continue_without_upgrade()
                    elif game.state == "boss_reward":
                        game.choose_boss_reward()
                    else:
                        game.state = "menu"

                elif game.state == "paused":
                    if event.key in (pygame.K_p, pygame.K_RETURN, pygame.K_SPACE):
                        game.state = game.paused_from
                    elif event.key == pygame.K_F5:
                        game.save()
                        game.show_message("ИГРА СОХРАНЕНА", 1.5)
                    elif event.key == pygame.K_m:
                        game.save()
                        game.state = "menu"

                elif game.state == "achievements":
                    if event.key in (pygame.K_ESCAPE, pygame.K_a):
                        game.state = "menu"

                elif game.state == "menu":
                    if event.key == pygame.K_a:
                        game.state = "achievements"
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        # If starting a run fails, keep the game from disappearing
                        # without an explanation and write the traceback to a log.
                        try:
                            game.start_game()
                        except Exception:
                            import traceback
                            with open(CRASH_LOG, "w", encoding="utf-8") as log:
                                log.write("Ошибка при запуске новой игры из меню (Enter):\n")
                                log.write(traceback.format_exc())
                            game.state = "menu"
                            game.show_message("ОШИБКА ЗАПУСКА: см. crash_log.txt", 5)
                    elif event.key == pygame.K_l:
                        game.load_save()

                elif game.state == "playing":
                    if event.key in (pygame.K_1, pygame.K_KP1, pygame.K_2, pygame.K_KP2,
                                     pygame.K_3, pygame.K_KP3, pygame.K_4, pygame.K_KP4):
                        key_to_weapon = {
                            pygame.K_1: 0, pygame.K_KP1: 0,
                            pygame.K_2: 1, pygame.K_KP2: 1,
                            pygame.K_3: 2, pygame.K_KP3: 2,
                            pygame.K_4: 3, pygame.K_KP4: 3,
                        }
                        game.player.weapon_index = key_to_weapon[event.key]
                        game.show_message(f"ОРУЖИЕ: {WEAPONS[game.player.weapon_index]['name']}", 1)

                    if event.key == pygame.K_e and game.exit_open:
                        side = game.door_side_at_player()
                        if side:
                            game.begin_room_transition(side)

                    if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
                        keys = pygame.key.get_pressed()
                        dx = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
                        dy = int(keys[pygame.K_s]) - int(keys[pygame.K_w])
                        game.player.dash(dx, dy)
                    elif event.key == pygame.K_g:
                        game.throw_grenade()
                    elif event.key == pygame.K_q:
                        game.use_shield()

                    if event.key == pygame.K_F5:
                        game.save()
                        game.show_message("ИГРА СОХРАНЕНА", 1.5)

                elif game.state == "shop":
                    shop_number_keys = {
                        pygame.K_1: 0, pygame.K_KP1: 0,
                        pygame.K_2: 1, pygame.K_KP2: 1,
                        pygame.K_3: 2, pygame.K_KP3: 2,
                        pygame.K_4: 3, pygame.K_KP4: 3,
                        pygame.K_5: 4, pygame.K_KP5: 4,
                        pygame.K_6: 5, pygame.K_KP6: 5,
                    }
                    if event.key in shop_number_keys:
                        game.shop_selected = shop_number_keys[event.key]
                        game.buy_shop_item()
                    elif event.key == pygame.K_LEFT:
                        game.shop_selected = (game.shop_selected - 1) % len(game.shop_options)
                    elif event.key == pygame.K_RIGHT:
                        game.shop_selected = (game.shop_selected + 1) % len(game.shop_options)
                    elif event.key == pygame.K_UP:
                        game.shop_selected = (game.shop_selected - 3) % len(game.shop_options)
                    elif event.key == pygame.K_DOWN:
                        game.shop_selected = (game.shop_selected + 3) % len(game.shop_options)
                    elif event.key == pygame.K_RETURN:
                        game.buy_shop_item()
                    elif event.key == pygame.K_e:
                        game.leave_shop()

                elif game.state == "upgrade":
                    if event.key in (pygame.K_1, pygame.K_KP1):
                        game.upgrade_selected = 0
                        game.choose_upgrade()
                    elif event.key in (pygame.K_2, pygame.K_KP2):
                        game.upgrade_selected = 1
                        game.choose_upgrade()
                    elif event.key in (pygame.K_3, pygame.K_KP3):
                        game.upgrade_selected = 2
                        game.choose_upgrade()
                    elif event.key == pygame.K_LEFT:
                        game.upgrade_selected = (game.upgrade_selected-1) % 3
                    elif event.key == pygame.K_RIGHT:
                        game.upgrade_selected = (game.upgrade_selected+1) % 3
                    elif event.key == pygame.K_RETURN:
                        game.choose_upgrade()
                    elif event.key == pygame.K_e:
                        game.continue_without_upgrade()

                elif game.state == "boss_reward":
                    if event.key in (pygame.K_1, pygame.K_KP1):
                        game.boss_reward_selected = 0
                        game.choose_boss_reward()
                    elif event.key in (pygame.K_2, pygame.K_KP2):
                        game.boss_reward_selected = 1
                        game.choose_boss_reward()
                    elif event.key in (pygame.K_3, pygame.K_KP3):
                        game.boss_reward_selected = 2
                        game.choose_boss_reward()
                    elif event.key == pygame.K_LEFT:
                        game.boss_reward_selected = (game.boss_reward_selected - 1) % 3
                    elif event.key == pygame.K_RIGHT:
                        game.boss_reward_selected = (game.boss_reward_selected + 1) % 3
                    elif event.key == pygame.K_RETURN:
                        game.choose_boss_reward()

                elif game.state == "gameover":
                    if event.key == pygame.K_RETURN:
                        game.start_game()
                    elif event.key == pygame.K_m:
                        game.state = "menu"

                elif game.state == "victory":
                    if event.key == pygame.K_RETURN:
                        game.start_game()

        game.update(dt)
        game.draw()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Keep a useful traceback when an unexpected error would otherwise
        # close the game window immediately.
        import traceback
        with open(CRASH_LOG, "w", encoding="utf-8") as log:
            log.write("Критическая ошибка DRONE HUNTER v5.38:\n")
            log.write(traceback.format_exc())
        try:
            pygame.quit()
        except Exception:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "DRONE HUNTER — ошибка",
                "Игра столкнулась с ошибкой. Подробности сохранены в crash_log.txt рядом с main.py."
            )
            root.destroy()
        except Exception:
            print("Игра столкнулась с ошибкой. Подробности сохранены в crash_log.txt.")
        raise
