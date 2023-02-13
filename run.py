#!/usr/bin/python
import atexit
import os
import sys
import json
import subprocess
import signal

#!FIXME эту штуку - в отдельный модуль, который будет запускальщиком параллельным
import time
project = ""
workflow = ""
running_tasks = []
root_path = "/opt/spa/data/"


class RunningTask(object):
    def __init__(self, task_name):
        self.task_name = task_name
        self.path = root_path + project + "/" + workflow + "/" + task_name
        self.pid = ""
        self.log = open(self.path + "/out", "w")
        self.err = open(self.path + "/err", "w")
        self.process = None
        self.set_json_status("not run")

    def task_json(self):
        with open(self.path + "/task.json", "r") as task_json_file:
            task_data = json.load(task_json_file)
        return task_data

    def run(self):
        print("RUN:", self.task_name)
        self.set_json_status("running")
        function_path = root_path + "/../bin/" + self.task_json()["task"]["function"]
        self.process = subprocess.Popen([function_path] + self.task_json()["task"]["params"],
                                        stdout=self.log, stderr=self.err, encoding='utf-8')
        self.pid = str(self.process.pid)
        open(self.path + "/pid", "w").write(self.pid)

    def wait_not_parallel(self):
        print("WAIT:", self.task_name)
        self.process.wait()
        # wait till end...
        os.remove(self.path + "/pid")
        status = self.renew_exec_status()
        self.set_json_status(status)
        self.log.close()
        self.err.close()

    def set_json_status(self,status):
        print("STATUS:", self.task_name, status)
        task_json_content = self.task_json()
        task_json_content["info"]["status"] = status
        with open(self.path + "/task.json", "w") as task_json_file:
            json.dump(task_json_content,task_json_file,indent=3)

    def renew_exec_status(self):
        json_status = self.task_json()["info"]["status"]
        if self.process:
            status = self.process.poll()
            if status is None:
                return "running"
            else:
                if status == 0:
                    if "pid" in os.listdir(self.path):
                        self.pid = ""
                        os.remove(self.path + "/pid")
                    return "success0"
                elif status > 0:
                    if "pid" in os.listdir(self.path):
                        self.pid = ""
                        os.remove(self.path + "/pid")
                    return "error" + str(status)
                elif status < 0:
                    if "pid" in os.listdir(self.path):
                        self.pid = ""
                        os.remove(self.path + "/pid")
                    return "terminated" + str(status)
        elif "pid" in os.listdir(self.path):
            pid = open(self.path + "/pid", "r").read()
            print("ERROR! pid file without process finded!", self.path, pid, " last status was", json_status, ". pid file removed, status \"not run\" supposed")
            os.remove(self.path + "/pid")
            return("not run")
        elif json_status == "running":
                print("ERROR! json status is \"running\", but no process finded, status \"not run\" supposed")
                return ("not run")
        else:
            return json_status #new, or earlier returned:success, error, terminated

    def stop_task(self): #Штатная остановка расчетной бесконечной задачи - при завершении воркфлоу
        print("STOP: stopping ",self.task_name)
        if self.process and "pid" in os.listdir(self.path):
            if self.process.poll() is None: #is running
                self.process.terminate()
                time.sleep(1)
                if self.process.poll() is None:  # is running
                    #self.process.terminate()
                    time.sleep(5)
                    if self.process.poll() is None:
                        self.kill_task()

        if "pid" in os.listdir(self.path):
            os.remove(self.path + "/pid")
        self.log.close()
        self.err.close()

    def kill_task(self): #грубое прибитие задачи
        print("KILL:", self.task_name)
        self.process.kill()
        time.sleep(1)
        if self.process.poll() is None:
            print("ERROR! can't kill subprocess, trying again... ", self.pid)
            self.process.kill()
            time.sleep(1)
            if self.process.poll() is None:
                print("ERROR! can't kill subprocess!", self.pid)
                return 1
                #!FIXME: а нужен ли эксепшен?
                #raise Exception("can't kill subprocess "+str(self.pid))
        return 0

    def __del__(self):
        print("DEL:", self.task_name)
        self.stop_task()

def clear_wf():
    path = root_path + project + "/" + workflow
    with open(path + "/workflow.json", "r") as wf_json_file:
        tasks = json.load(wf_json_file)  # os.listdir(root_path + project + "/" + workflow)
    task_names = [t["name"] for t in tasks]
    for t in task_names:
        task_path = path + "/" + t
        if "pid" in os.listdir(task_path):
            print("WARNING: pid file exists in", t)
            os.remove(task_path + "/pid")

def run_task(task_name):
    new_task = RunningTask(task_name)
    new_task.run()
    if new_task.task_json()["task"]["exec"] == "await":
        new_task.wait_not_parallel()
        return None
    else:
        print("running in parallel")
        running_tasks.append(new_task)
        return new_task

def kill_all_tasks():
    for t in running_tasks:
        t.stop_task()
    with open(root_path + project + "/" + workflow + "/workflow.json", "r") as wf_json_file:
        wf_tasks = json.load(wf_json_file) # os.listdir("/opt/spa/data/" + project + "/" + workflow)
    wf_path = root_path + project + "/" + workflow
    for task_dir in os.listdir(wf_path):
        if os.path.isdir(os.path.join(wf_path,task_dir)):
            if not task_dir in wf_tasks: # если какие-то таски не попали в json wf
                if "pid" in os.listdir(os.path.join(wf_path,task_dir)):
                    pid = open(wf_path + "/" + task_dir + "/pid", "r").read()
                    print ("ERROR: Can't stop unknown process with pid:", pid, "in task", task_dir)
                    #!FIXME а может быть за это время этот пид перешел к другому процессу?
                    #os.kill(int(pid), signal.SIGKILL)

def review_statuses():
    # собрать по всем таскам их текущий статус настоящий, заодно убирая pid файлы умерших - и записать их в json тасков
    for task in running_tasks:
        old_status = task.task_json()["info"]["status"]
        new_status = task.renew_exec_status()
        if new_status != old_status:
            task.set_json_status(new_status)
        if new_status != "running":
            running_tasks.remove(task)
    # собрать инфу из json тасков - в json workflow
    path = root_path + project + "/" + workflow + "/"
    with open(path+"workflow.json", "r") as fp:
        wf_tasks = json.load(fp)
    for t in wf_tasks:
        json_task_path = path + t["name"]
        with open(json_task_path + "/task.json", "r") as task_json_file:
            task_json = json.load(task_json_file)
        t["status"] = task_json["info"]["status"]
    with open(path+"workflow.json", "w") as fp:
        json.dump(wf_tasks,fp,indent=3)


def handler_killer(signum, frame):
    print("STOP: \n Stoping workflow execution with signal", signum)
    print("frame:", frame)
    kill_all_tasks()
    exit(0)


signal.signal(signal.SIGTERM,handler_killer)
signal.signal(signal.SIGINT,handler_killer)
signal.signal(signal.SIGALRM,handler_killer)
signal.signal(signal.SIGQUIT,handler_killer)
signal.signal(signal.SIGABRT,handler_killer)
signal.signal(signal.SIGHUP,handler_killer)
# Штука опасная, так как может быть асинхронной - и вот, нате, гонка за файл воркфлоу. Поэтому игнорируем  - в итоге зомбей не будет
signal.signal(signal.SIGCHLD,signal.SIG_IGN)
atexit.register(kill_all_tasks)

if __name__ == "__main__":
    data = json.loads(sys.argv[1])
    project = data["project"]
    workflow = data["workflow"]
    try:
        if "task" in data:
            if run_task(data["task"]) is not None:
                while running_tasks:
                    review_statuses()
                    time.sleep(5)
            #return Success({"answer": stdout})
        else:
            #run wf
            clear_wf()
            with open(root_path + project + "/" + workflow + "/workflow.json", "r") as wf_json_file:
                tasks = json.load(wf_json_file)#os.listdir(root_path + project + "/" + workflow)
            task_names = [t["name"] for t in tasks]
            for task in tasks:
                run_task(task["name"])

            while running_tasks:
                review_statuses()
                time.sleep(5)

    #except KeyboardInterrupt:
    #    print("keyboard interrupt")
    #    kill_all_tasks()
    #except SystemExit:
    #    print("sys exit")
    #    kill_all_tasks()
    finally:
        print("STATUS: workflow ", workflow, "is stopped")
        kill_all_tasks()

