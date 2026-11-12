DRONE HUNTER v5.38 — сборка Windows EXE через GitHub

Результат: DRONE_HUNTER.exe. На компьютере для запуска игры Python не нужен.

КАК ПОЛУЧИТЬ EXE (один раз):
1. Открой https://github.com и войди в аккаунт (если аккаунта нет — создай).
2. Нажми + вверху справа -> New repository.
3. Назови репозиторий DRONE-HUNTER, выбери Public или Private и нажми Create repository.
4. На странице репозитория нажми Add file -> Upload files.
5. Распакуй этот ZIP на компьютере и перетащи ВСЕ его содержимое в окно GitHub.
   Важно: вместе с main.py и requirements.txt загрузи папку .github.
   Если папка .github не видна в проводнике, включи отображение скрытых элементов.
6. Нажми Commit changes.
7. Открой вкладку Actions -> Build Windows EXE. Дождись зелёной галочки.
8. Открой завершённый запуск workflow, внизу найди Artifacts и скачай DRONE_HUNTER-Windows.
9. Распакуй скачанный ZIP. Внутри будет DRONE_HUNTER.exe.
10. Создай ярлык: правой кнопкой по EXE -> Показать дополнительные параметры -> Создать ярлык.

Если workflow не запустился автоматически:
Actions -> Build Windows EXE -> Run workflow -> Run workflow.

Сохранения save.json, pilot_profile.json и crash_log.txt будут находиться рядом с EXE.
Не запускай EXE прямо из ZIP — сначала распакуй его в отдельную папку.

Примечание: GitHub Actions собирает файл на Windows. Это не означает, что игра уже была протестирована на твоём ПК; после сборки запусти EXE и сообщи, если появится ошибка.
