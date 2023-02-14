#!/usr/bin/python
import atexit
import os
import sys
import json
import subprocess
import signal
import time
project = ""
workflow = ""
running_tasks = set()

root_path = "/opt/spa/data/"
terminate_flag = 0

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
        # global current_await_task
        # current_await_task = self
        #self.process.communicate()
        while self.process.poll() is None:
            if terminate_flag == 1:
                print("STOP: Terminating current task", self.task_name)
                self.stop_task()
                return
            else:
                review_statuses()
                time.sleep(2)

        # wait till end...
        # current_await_task = None
        self.pid = ""
        if os.path.isfile(self.path + "/pid"):
            os.remove(self.path + "/pid")
        status = self.examine_exec_status()
        self.set_json_status(status)
        self.log.close()
        self.err.close()
        running_tasks.remove(self)

    def set_json_status(self,status):
        print("STATUS:", self.task_name, status)
        task_json_content = self.task_json()
        task_json_content["info"]["status"] = status
        with open(self.path + "/task.json", "w") as task_json_file:
            json.dump(task_json_content,task_json_file,indent=3)

    def examine_exec_status(self):
        json_status = self.task_json()["info"]["status"]
        if self.process:
            status = self.process.poll()
            if status is None:
                return "running"
            else:
                if os.path.isfile(self.path + "/pid"):
                    self.pid = ""
                    os.remove(self.path + "/pid")
                if status == 0:
                    return "success0"
                elif status > 0:
                    return "error" + str(status)
                elif status < 0:
                    return "terminated" + str(status)
        elif "pid" in os.listdir(self.path):
            pid = open(self.path + "/pid", "r").read()
            print("ERROR! pid file without process finded!", self.path, pid, " last status was", json_status, ". pid file removed, status \"not run\" supposed")
            os.remove(self.path + "/pid")
            return "not run"
        elif json_status == "running":
                print("ERROR! json status is \"running\", but no process finded, status \"not run\" supposed")
                return "not run"
        else:
            return json_status #new, or earlier returned:success, error, terminated

    def stop_task(self): #Штатная остановка расчетной бесконечной задачи - при завершении воркфлоу
        print("STOP: stopping ",self.task_name)
        self.set_json_status("stopping")
        if self.process and "pid" in os.listdir(self.path):
            if self.process.poll() is None: #is running
                self.process.send_signal(signal.SIGTERM)
                time.sleep(1)
                if self.process.poll() is None:  # is running
                    #self.process.terminate()
                    time.sleep(5)
                    print("st2", self.process.poll())
                    if self.process.poll() is None:
                        self.kill_task()
                        self.set_json_status("killed")
                    else:
                        self.set_json_status("stopped")
                else:
                    self.set_json_status("stopped")
            else:
                self.set_json_status("stopped")

        if "pid" in os.listdir(self.path):
            os.remove(self.path + "/pid")
        self.log.close()
        self.err.close()
        print("ret", self.process.returncode)
        print("STOP: stopped ", self.task_name, self.process.poll())

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
        print("DELETING:", self.task_name)
        if self in running_tasks:
            self.stop_task()
            #running_tasks.remove(self)
        print("DEL:", self.task_name)


def clear_wf():
    path = root_path + project + "/" + workflow
    with open(path + "/workflow.json", "r") as wf_json_file:
        wf_tasks = json.load(wf_json_file)  # os.listdir(root_path + project + "/" + workflow)
    wf_task_names = [t["name"] for t in wf_tasks]
    for t in wf_task_names:
        task_path = path + "/" + t
        if "pid" in os.listdir(task_path):
            print("WARNING: pid file exists in", t)
            os.remove(task_path + "/pid")


def run_task(task_name):
    new_task = RunningTask(task_name)
    new_task.run()
    running_tasks.add(new_task)
    if new_task.task_json()["task"]["exec"] == "await":
        new_task.wait_not_parallel()
        return None
    else:
        print("running in parallel")
        return new_task


def stop_all_tasks():
    global running_tasks
    if len(running_tasks) == 0:
        return
    print("KILL!!!")
    print([t.task_name for t in running_tasks])
    for t in running_tasks:
        t.stop_task()
    #running_tasks -= tasks_for_remove
    #tasks_for_remove.clear()
    #print("KILL: Remaine", len(running_tasks),"tasks")
    #running_tasks.clear()
    with open(root_path + project + "/" + workflow + "/workflow.json", "r") as wf_json_file:
        wf_tasks = json.load(wf_json_file) # os.listdir("/opt/spa/data/" + project + "/" + workflow)
    wf_path = root_path + project + "/" + workflow
    for task_dir in os.listdir(wf_path):
        if os.path.isdir(os.path.join(wf_path, task_dir)):
            if "pid" in os.listdir(os.path.join(wf_path,task_dir)):
                pid = open(wf_path + "/" + task_dir + "/pid", "r").read()
                print ("ERROR: Can't stop unknown process with pid:", pid, "in folder", task_dir)
    review_statuses()

def kill_all_tasks():
    print("ERROR: terminating all tasks")
    global terminate_flag
    terminate_flag = 1
    for t in running_tasks:
        t.process.terminate()
    time.sleep(5)
    for t in running_tasks:
        t.process.poll()

def review_statuses():
    # собрать по всем таскам их текущий статус настоящий, заодно убирая pid файлы умерших - и записать их в json тасков
    print("INFO: review status")
    global running_tasks
    tasks_for_remove = set()
    for t in running_tasks:
        old_status = t.task_json()["info"]["status"]
        new_status = t.examine_exec_status()
        if new_status != old_status:
            t.set_json_status(new_status)
        if new_status != "running":
            tasks_for_remove.add(t)
    running_tasks -= tasks_for_remove
    tasks_for_remove.clear()
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


def handler_stop(signum, frame):
    print("STOP: \n Stopping workflow execution with signal", signum)
    print("frame:", frame)
    # if current_await_task is not None:
    #     current_await_task.stop_task()
    #     running_tasks.remove(current_await_task)
    global terminate_flag
    terminate_flag = 1


def handler_killer(signum, frame):
    print("STOP: \n Killing workflow execution with signal", signum)
    print("frame:", frame)
    kill_all_tasks()
    exit(1)

def handler_child_death(signum, frame):
    if not terminate_flag:
        for t in running_tasks:
            t.process.poll()

#soft stop at next cycle iteration
signal.signal(signal.SIGUSR1,handler_stop)
#sigterm all tasks
signal.signal(signal.SIGTERM,handler_killer)
signal.signal(signal.SIGINT,handler_killer)
signal.signal(signal.SIGALRM,handler_killer)
signal.signal(signal.SIGQUIT,handler_killer)
signal.signal(signal.SIGABRT,handler_killer)
signal.signal(signal.SIGHUP,handler_killer)
#signal.signal(signal.SIGCHLD,signal.SIG_IGN)
signal.signal(signal.SIGCHLD,handler_child_death)

atexit.register(stop_all_tasks)

if __name__ == "__main__":
    data = json.loads(sys.argv[1])
    project = data["project"]
    workflow = data["workflow"]
    #try:
    if True:

        if "task" in data:
            if run_task(data["task"]) is not None:
                while len(running_tasks) > 0:
                    review_statuses()
                    time.sleep(5)
            #return Success({"answer": stdout})
        else:
            print("run wf")
            clear_wf()
            with open(root_path + project + "/" + workflow + "/workflow.json", "r") as wf_json_file:
                tasks = json.load(wf_json_file)#os.listdir(root_path + project + "/" + workflow)
            task_names = [t["name"] for t in tasks]
            for task in tasks:
                if terminate_flag == 1:
                    print("STOP: Ignoring remaining tasks")
                    break
                run_task(task["name"])
            while len(running_tasks) > 0:
                if terminate_flag == 1:
                    print("STOP: Stopping the workflow execution cycle")
                    stop_all_tasks()
                    break
                review_statuses()
                time.sleep(5)

    #except KeyboardInterrupt:
    #    print("keyboard interrupt")
    #    kill_all_tasks()
    #except Exception:
    #    print("sys exit")
    #    kill_all_tasks()
    #finally:
    #    kill_all_tasks()
    #    print("STATUS: workflow ", workflow, "is stopped")

