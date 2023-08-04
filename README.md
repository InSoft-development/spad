# spad
## Терминология
### project
анализируемая установка, проект целиком, объект, куда мы поставляем нашу разработку. Одна поставка - один проект. Сосуществование на одной железке двух разных проектов пока не рассматривается и не тестриуется, хотя такие возможности закладываются.
### task
исполняемый файл с его набором параметров для запуска.
### workflow
алгоритм анализа, состоящий из набора последовательных и параллельных тасков - запусков исполняемых файлов. Часть можно запустить в фоне, остальное - одно за другим. Это может быть и некоторый конечный расчет - который будет завершен -  или непрерывный процесс анализа. Мы не рассчитываем на обязательное штатное завершение работы workflow: оно может работать “вечно”. При падении с ошибкой какого либо таска - он будет однократно перезапущен (впоследствии - многократно). Если последовательность тасков из списка закончит исполнение - будут ожидаться параллельно запущенные таски. При отключении железки - при перезапуске системы - будут перезапускаться те воркфлоу, которые были запущены, но не завершены.

## Файлы в репозитории
* srv.py - Сервер запуска приложений. JSON-RPC. Запускается без параметров. Всё хранит в /opt/spa
* run.py - скрипт, запускающийся сервером в отдельном процессе и исполняющий воркфлоу. Пораждает процессы, которые запускают таски, работающие в параллель. Останавливается штатно командой stop из srv.py - сигналом SIGUSR1. Все остальные попытки его убить - убивают его жестко. Останов занимает довольно долгое время, так как может ожидать штатной остановки тасков.
* spa_conn - фронтенд для работы с srv.py не через curl - чуть-чуть удобнее.
* simple, error, wait - простые баш скрипты для тетирования работы воркфлоу, хранятся вместе со всеми бинарями - как ссылки - в /opt/spa/bin - туда же надо сложить ссылки на все используемые бинари (ну или сами бинари)
* command_*.json - json файлы для тестирования с помощью curl или spa_ctl
* alarms.py - скрипт, отслеживающий в базе данных сигналы об аномалиях и добавляющий некоторую логику к обработке их - логирование, записи в отдельную таблицу. Ему тут не место, впринципе, и в целом решение такое себе...

## JSON файл, используемый для создания и редактирования workflow
Пример
```
{
    "project": {
        "id": 1,
        "name": "pr1",
        "workflows": [
            {
                "id": 1,
                "name": "wf1",
                "tasks": [
                    {
                        "id": 1,
                        "name": "t11",
                        "place": 1,
                        "exec": "parallel",
                        "function": "simple",
                        "params": [
                            "0"
                        ],
                        "status": "something"
                    }
                ]
            }
        ]
    }
}
```

# spa_conn
## Команды spa_conn

### select_project
_spa_сonn select_project < project name>_

Параметр - имя проекта. На данный момент не тестировалась возможность работы с двумя проектами с одной машины. Но рекомендуется явно выбрать проект, прежде чем начать работу.

### create
_spa_сonn create (-j < json string> | -f < json file>)_

Создание и дополнение проекта новыми воркфлоу и тасками по указанным конфиграциям json, имеющему древовидную структуру.
Параметром полный json в виде строки в кавычках - или файла, со всеми полями. Если проект или воркфлоу, указанные в json уже существуют - таски (или новые воркфлоу) будут добавлены туда. Проект, указанный в json - запоминается как текущий проект. Нумерация новых тасков “подвинет” уже существующие вниз. Осуществляется выбор проекта из json

### delete
_spa_сonn delete (-j < json string> | -f < json file>)_

Удаление существующих тасков и воркфлоу, чьи имена будут “листьями” дерева в json.
Параметром json-дерево. Полный json чего хотим удалить до уровня, на котором будем удалять: task или workflow - на ком дерево обрывается - того и удаляем. Запущенное - удалять нельзя. Только остановленное. Project - удалять нельзя, так как он соответствует объекту материального мира, существующему помимо нашего желания его удалить. Проект, указанный в json - запоминается как текущий проект.
(переделаю на возможность указания упрощенно - через опции project-wf-task)
(можно последовательно в одном json удалять по нескольку раз таски и даже воркфлоу. Там последовательный перебор с удалением.)

### update
_spa_сonn update -j < json string> | -f < json file>_

Параметром json дерево. Запущенное - изменять нельзя. Только остановленное. Выполняется как последовательный delete и create. Таким образом, нет возможности изменить один параметр - надо изменять целиком всю сущность, указывая все ее параметры. Для удобства - использовать dump для получения текущей конфигурации.

### run
_spa_сonn run -p <project> -w < workflow> (-t < task>)_

Запуск на исполнение workflow. Workflow исполняется согласно его json файлу. Исполнение последовательности тасков происходит в отдельном процессе линукса. Параллельные таски - отстреливаются в еще отдельнгые дочерние процессы. Указанный project будет запомнен как текущий. Запускать параллельно можно любое количество воркфлоу - до ограничений системы.

### stop
_spa_сonn stop -w < workflow>_

указать workflow (указывать проект не обязательно - так как предполагается, что мы работаем только с одним проектом на одном сервере, и воркфлоу будет найдено среди списка уже запущенных). Остановки отдельных тасков нет. Остановка отдельного последовательного таска с перескоком на следующий не осуществляется - так как предполагается зависимость между последовательно исполняемыми тасками. Остановка параллельно исполняемого таска так же не осуществляется - так как предполагается, что без его работы - будет невозможно исполнение текущего таска из последовательных.

### status
_spa_сonn status -p < project> -w < workflow> (-t < task>)_

Запрос статусов текущих исполняемых процессов в workflow.
Указать project и workflow обязательно, можно указать task
Статусы возможны следующие:
* new - устанавливается всем в начале запуска workflow, затирая статусы с прошлого запуска
* not run - при чтении таска из его файла
* running - исполняется в данный момент
* waiting - экспериментальный статус, который возможно установить через set_status, означающий долгие вычисления во внешней библиотеке, во время которых таск нельзя завершать или убивать штатными средствами. Пока нет ясности в его функциональности и не до конца оттестирован.
* error(+code) - завершился с ошибкой, означенной кодом (линуксовый код завершения процесса больше нуля)
* rerun - перезапуск после завершения с ошибкой. На данный момент - однократный. Так как не смог реализовать простого и надежного механизма подсчета попыток перезапуска.
* success0 - завершен без ошибок (код ноль)
* terminated(-code) - завершен внешним сигналом (код возврата меньше нуля).
* stopping - начало процесса остановки таска
* stopped - успешно остановлен нами спустя максимум - 6 секунд после начала процесса остановки.
* killed - не удалось остановить (подвис) - послан сигнал terminate
* immortal(pid) - не завершился после сигнала terminate, оставляем попытки его убить. Дальнейшее отслеживание - по выданному pid.

### dump
_spa_сonn status -p < project> -w < workflow> (-t < task >)_

Возвращает существующую конфигурацию проекта, воркфлоу или таска в виде json
Указать project и workflow обязательно, можно указать task
Его результат можно использовать для команды update.

### set_status
_spa_сonn status -p < project > -w < workflow > -t < task >_

Принудительная установка некоторого статуса указанному таску.
Создана для возможности установить статус waiting при входе во внешнюю библиотеку, во время работы в которой - процесс нельзя трогать. Тестировалось мало.

### file
Копирование файлов на и с сервера.

_spa_сonn file --upload < file >_

Загрузка локального файла на сервер spad. Если не указано пути - в дирректорию, где работает spad.

_spa_сonn file --download < file >_

Скачивание файла с сервера spad на локальную файловую систем. Если не указано путей - из дирректории, где работает spad в дирректорию, где работает spa_ctl на локальной машине.

_spa_сonn file --move < file1> < file2 >_

Перемещение файла. Можно перемещать только в дирректории тасков (/opt/spa/data/<pr>/<wf>/<t>) или в /opt/spa/bin/ . Таким образом рекомендуется закидывать конфиги и веса после обучения в целевые папки, где будут запускаться исполняемые файлы, если эти файлы не планируется помещать под систему контроля версий - а генерировать каждый раз заново.

_spa_сonn file --link < file1> < file2 >_

Создание символической ссылки f2 -> f1. Можно создавать только в дирректориях тасков (/opt/spa/data/<pr>/<wf>/<t>) или в /opt/spa/bin/. Рекомендуется таким образом использовать ссылки на наши исполняемые файлы и прочие модули питона из папок, содержащих git репзитории - для использования их в spad. Так же таким образом рекомендуется закидывать файлы с ценными конфигами или весами, которые предполагается переиспользовать впоследствии, чтобы не создавать их неучтенных копий.

# Пример работы

Допустим, у нас есть алгоритм анализа со следующими шагами:
0. Предполагаем, что данные уже лежат в БД, доступ до них прописан в самих скриптах - spad не система прямой работы с данными
1. Запустить скрипт demo.py, который выдаст некоторый демонстрационный режим для первичной обработки данных
2. По изученному, мы руками у себя создаем файл intervals.json с ыделенными интервалами обучения
3. Закидываем файл на машину
4. Запускаем скрипт learn.py, который обучает наш метод и на выходе генерирует файл weight.json
5. Перемещаем полученный файл к себе в /home для дальнейшей повторной работы с ним
6. Запускаем в параллельном фоновом потоке скрипт pred.py осуществляющий "на лету" предобработку данных, идущих потоком в БД
7. Запускаем в параллельном фоновом потоке скрипт method.py, осуществляющий анализ предобработанных данных
8. Запускаем в параллельном фоновом потоке скрипт post.py осуществляющий постобработку проанализированных данных
9. Запускаем в параллельном фоновом потоке скрипт alarms.py осуществляющий слежение за ситуациями аномалии по результатам постобработки.
10. Запускаем в фоне веб-приложение мониторинга run_dashboard.py

Для этого надо создать три workflow файла:
1. demo.json - запуск фронтенда в виде веб-сервера.
```
{
    "project": {
        "id": 1,
        "name": "my_project",
        "workflows": [
            {
                "id": 1,
                "name": "demo",
                "tasks": [
                    {
                        "id": 1,
                        "name": "demo",
                        "place": 1,
                        "exec": "await",
                        "function": "demo.py",
                        "params": []
                    }
                ]
            }
        ]
    }
}
```
3. learn.json - запускаем, ждем, отрабатывает, сам останавливается
```
{
    "project": {
        "id": 1,
        "name": "my_project",
        "workflows": [
            {
                "id": 1,
                "name": "learn",
                "tasks": [
                    {
                        "id": 1,
                        "name": "learn",
                        "place": 1,
                        "exec": "await",
                        "function": "learn.py",
                        "params": [
                            "-w",
                            "weight.json"
                        ],
                    }
                ]
            }
        ]
    }
}
```
5. analyse.json - запускает последовательно все шаги анализа - отстреливая их в параллельные потоки
```
{
    "project": {
        "id": 1,
        "name": "my_project",
        "workflows": [
            {
                "id": 1,
                "name": "analyse",
                "tasks": [
                    {
                        "id": 1,
                        "name": "pred",
                        "place": 1,
                        "exec": "parallel",
                        "function": "pred.py",
                        "params": [],
                    },
                    {
                        "id": 1,
                        "name": "method",
                        "place": 1,
                        "exec": "parallel",
                        "function": "method.py",
                        "params": [
                            "-w",
                            "weight.json"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "post",
                        "place": 1,
                        "exec": "parallel",
                        "function": "post.py",
                        "params": [],
                    },
                    {
                        "id": 1,
                        "name": "alarms",
                        "place": 1,
                        "exec": "parallel",
                        "function": "alarms.py",
                        "params": [
                            "96"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "dashboard",
                        "place": 1,
                        "exec": "parallel",
                        "function": "run_dashboard.py",
                        "params": [],
                    }
                ]
            }
        ]
    }
}
```

После чего выполнить следующие команды:
1. _spa_conn create --file demo.json_ #создаем воркфлоу
2. _spa_conn create --file learn.json_ #создаем воркфлоу
3. _spa_conn create --file analyse.json_ #создаем воркфлоу
4. _spa_conn run --project my_project --wf demo_ #запуск первого воркфлоу
5. Изучаем данные в веб странице у себя локально, записываем пометки по разметке в текстовый файл у себя локально
6. _spa_conn stop --wf demo_ #останов
7. _spa_conn file --upload intervals.json_ #закидываем наш файлик
8. _spa_conn file --move intervals.json /home/my_user/intervals_v1.json_ #перемещаем его на удаленной машине в home
9. _spa_conn file --link /home/my_user/intervals_v1.json /opt/spa/data/my_project/learn/learn_task/intervals.json_ #кладем ссылку на него в нужную папку
10. _spa_conn run --wf learn_ #запуск обучения
11. ожидаем окончания, периодически посматривая статус следующей командой
12. _spa_conn status --wf learn_
13. когда исполнение окончилось успешно - переходим к анализу
14. _spa_conn run --wf analyse_ #запуск онлайн анализа со всем множеством скриптов
15. производим мониторинг работы через веб интерфейс в run_dashboard

В дальнейшем - мы хотим объединить все workflow в один, когда, допустим, автоматизировали отбор интервалов - и написали простейшие баш скрипты для перекладывания файла интервалов весов в home - с созданием симлинка в нужные места после обучения: mv1.sh, mv2.sh
```
{
    "project": {
        "id": 1,
        "name": "my_project",
        "workflows": [
            {
                "id": 1,
                "name": "learn_and_run",
                "tasks": [
                    {
                        "id": 1,
                        "name": "find_intervals",
                        "place": 1,
                        "exec": "await",
                        "function": "intervals_automation.py",
                        "params": [
                            "intervals.json"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "mv_intervals",
                        "place": 1,
                        "exec": "await",
                        "function": "mv1.sh",
                        "params": [
                            "weight.json"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "learn",
                        "place": 1,
                        "exec": "await",
                        "function": "learn.py",
                        "params": [
                            "-w",
                            "weight.json"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "mv_weights",
                        "place": 1,
                        "exec": "await",
                        "function": "mv2.sh",
                        "params": [
                            "weight.json"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "pred",
                        "place": 1,
                        "exec": "parallel",
                        "function": "pred.py",
                        "params": [],
                    },
                    {
                        "id": 1,
                        "name": "method",
                        "place": 1,
                        "exec": "parallel",
                        "function": "method.py",
                        "params": [
                            "-w",
                            "weight.json"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "post",
                        "place": 1,
                        "exec": "parallel",
                        "function": "post.py",
                        "params": [],
                    },
                    {
                        "id": 1,
                        "name": "alarms",
                        "place": 1,
                        "exec": "parallel",
                        "function": "alarms.py",
                        "params": [
                            "96"
                        ],
                    },
                    {
                        "id": 1,
                        "name": "dashboard",
                        "place": 1,
                        "exec": "parallel",
                        "function": "run_dashboard.py",
                        "params": [],
                    }
                ]
            }
        ]
    }
}
```
И запуск упрощается:

_spa_conn create -f learn_and_run.json_
_spa_conn run -p my_project -w learn_and_run_

Но падает на втором таске - и нам приходится возвращаться к первому варианту, так как он стабильнее =)
