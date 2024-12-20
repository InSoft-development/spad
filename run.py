#!/usr/bin/python
import atexit
import os
import sys
import json
import subprocess
import signal
import time
import requests
import logging
import datetime

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
        self.log = open(self.path + "/log", "w")
        self.process = None
        self.set_json_status("not run")

    def task_json(self):
        with open(self.path + "/task.json", "r") as task_json_file:
            task_data = json.load(task_json_file)
        return task_data

    def run(self):
        logging.info(datetime.datetime.now().isoformat() + ": RUN:" + self.task_name)
        self.set_json_status("running")
        if self.task_json()["task"]["function"][-3:] == ".py":
            function_path = "python"
            params = [str(root_path + "/../bin/" + self.task_json()["task"]["function"])] + self.task_json()["task"]["params"]
        elif self.task_json()["task"]["function"][-3:] == ".sh":
            function_path = "bash"
            params = [str(root_path + "/../bin/" + self.task_json()["task"]["function"])] + self.task_json()["task"]["params"]
        else:
            function_path = str(root_path + "/../bin/" + self.task_json()["task"]["function"])
            params = self.task_json()["task"]["params"]
            if not os.path.isfile(function_path):
                function_path = self.task_json()["task"]["function"]
        logging.info(datetime.datetime.now().isoformat() + ": RUN:" + function_path + ' ' +  ' '.join(str(i) for i in params))
        self.process = subprocess.Popen([function_path] + params,
                                        stdout=self.log, stderr=self.log, encoding='utf-8',
                                        cwd=self.path)
        self.pid = str(self.process.pid)
        open(self.path + "/pid", "w").write(self.pid)

    def rerun(self):
        logging.info(datetime.datetime.now().isoformat() + ": RERUN:" + self.task_name)
        self.set_json_status("rerun")
        if self.task_json()["task"]["function"][-3:] == ".py":
            function_path = "python"
            params = [str(root_path + "/../bin/" + self.task_json()["task"]["function"])] + self.task_json()["task"][
                "params"]
        elif self.task_json()["task"]["function"][-3:] == ".sh":
            function_path = "bash"
            params = [str(root_path + "/../bin/" + self.task_json()["task"]["function"])] + self.task_json()["task"][
                "params"]
        else:
            function_path = str(root_path + "/../bin/" + self.task_json()["task"]["function"])
            params = self.task_json()["task"]["params"]
            if not os.path.isfile(function_path):
                function_path = self.task_json()["task"]["function"]
        self.process = subprocess.Popen([function_path] + params,
                                        stdout=self.log, stderr=self.log, encoding='utf-8',
                                        cwd=self.path)
        self.pid = str(self.process.pid)
        open(self.path + "/pid", "w").write(self.pid)

    def wait_not_parallel(self):
        logging.info(datetime.datetime.now().isoformat() + ": WAIT NOT PARALLEL:" + self.task_name)
        # global current_await_task
        # current_await_task = self
        #self.process.communicate()
        while self.process.poll() is None:
            if terminate_flag == 1:
                logging.info(datetime.datetime.now().isoformat() +": STOP: Terminating current task" + self.task_name)
                self.stop_task()
                return "stopped"
            else:
                review_statuses()
                time.sleep(2)
        review_statuses() #rerun can probably be acured here
        while self.process.poll() is None:
            if terminate_flag == 1:
                logging.info(datetime.datetime.now().isoformat() + ": STOP: Terminating current task" + self.task_name)
                self.stop_task()
                return "stopped"
            else:
                review_statuses()
                time.sleep(2)

        self.pid = ""
        if os.path.isfile(self.path + "/pid"):
            os.remove(self.path + "/pid")
        status = self.examine_exec_status()
        self.set_json_status(status)
        review_statuses()
        return status

    def set_json_status(self,status):
        logging.info(datetime.datetime.now().isoformat() + ": STATUS:" + self.task_name + " " + str(status))
        task_json_content = self.task_json()
        task_json_content["info"]["status"] = status
        with open(self.path + "/task.json", "w") as task_json_file:
            json.dump(task_json_content,task_json_file,indent=3)

    def examine_exec_status(self):
        json_status = self.task_json()["info"]["status"]
        if self.process:
            status = self.process.poll()
            if status is None:
                if json_status == "waiting":
                    return json_status
                if "rerun" in json_status:
                    return json_status
                else:
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
            logging.info(datetime.datetime.now().isoformat() + ": ERROR! pid file without process finded!"
                         + self.path +" " +  str(pid)
                         + " last status was" + str(json_status) + ". pid file removed, status \"not run\" supposed")
            os.remove(self.path + "/pid")
            return "not run"
        elif json_status == "running":
                logging.info(datetime.datetime.now().isoformat() +
                             ": ERROR! json status is \"running\", but no process finded, status \"not run\" supposed")
                return "not run"
        else:
            return json_status #new, or earlier returned:success, error, terminated

    def stop_task(self): #Штатная остановка расчетной бесконечной задачи - при завершении воркфлоу
        if self.examine_exec_status() == "waiting":
            logging.info(datetime.datetime.now().isoformat() + ": CAN'T STOP: waiting" + self.task_name)
            return
        logging.info(datetime.datetime.now().isoformat() + ": STOP: stopping " + self.task_name)
        self.set_json_status("stopping")
        if self.process and "pid" in os.listdir(self.path):
            if self.process.poll() is None: #is running
                self.process.send_signal(signal.SIGTERM)
                time.sleep(1)
                if self.process.poll() is None:  # is running
                    #self.process.terminate()
                    time.sleep(5)
                    logging.info(datetime.datetime.now().isoformat() + ": st2 " + str(self.process.poll()))
                    if self.process.poll() is None:
                        if self.kill_task() != 1:
                            self.set_json_status("killed")
                        else:
                            logging.info(datetime.datetime.now().isoformat() + ": ERROR! Immortal task! " + str(self.pid))
                            self.set_json_status("immortal"+self.process.pid)
                            return
                    else:
                        self.set_json_status("stopped")
                else:
                    self.set_json_status("stopped")
            else:
                self.set_json_status("stopped")

        if "pid" in os.listdir(self.path):
            os.remove(self.path + "/pid")
        logging.info(datetime.datetime.now().isoformat() + ": ret " + str(self.process.returncode))
        logging.info(datetime.datetime.now().isoformat() + ": STOP: stopped " + self.task_name +
                     " " + str(self.process.poll()))

    def kill_task(self): #грубое прибитие задачи
        logging.info(datetime.datetime.now().isoformat() + ": KILL:" + self.task_name)
        self.process.kill()
        time.sleep(1)
        if self.process.poll() is None:
            logging.info(datetime.datetime.now().isoformat() + ": ERROR! can't kill subprocess, trying again... "
                         + str(self.pid))
            self.process.kill()
            time.sleep(1)
            if self.process.poll() is None:
                logging.info(datetime.datetime.now().isoformat() + ": ERROR! can't kill subprocess! " + str(self.pid))
                return 1
                #!FIXME: а нужен ли эксепшен?
                #raise Exception("can't kill subprocess "+str(self.pid))
        return 0

    def __del__(self):
        logging.info(datetime.datetime.now().isoformat() + ": DELETING:" + self.task_name)
        if self in running_tasks:
            self.stop_task()
        self.log.close()
        logging.info(datetime.datetime.now().isoformat() + ": DEL:" + self.task_name)


def clear_wf():
    path = root_path + project + "/" + workflow
    with open(path + "/workflow.json", "r") as wf_json_file:
        wf_tasks = json.load(wf_json_file)  # os.listdir(root_path + project + "/" + workflow)
    wf_task_names = [t["name"] for t in wf_tasks]
    for i in range(len(wf_tasks)):
        wf_tasks[i]["status"] = "new"
    for t in wf_task_names:
        task_path = path + "/" + t
        if "pid" in os.listdir(task_path):
            logging.info(datetime.datetime.now().isoformat() + ": WARNING: pid file still exists in " + str(t))
            os.remove(task_path + "/pid")
        with open(task_path + "/task.json", "r") as task_json_file:
            task_json_content = json.load(task_json_file)
            task_json_content["info"]["status"] = "new"
        with open(task_path + "/task.json", "w") as task_json_file:
            json.dump(task_json_content, task_json_file, indent=3)
    with open(path+"/workflow.json", "w") as fp:
        json.dump(wf_tasks, fp, indent=3)

# def resume_wf():
#     path = root_path + project + "/" + workflow
#     with open(path + "/workflow.json", "r") as wf_json_file:
#         wf_tasks = json.load(wf_json_file)  # os.listdir(root_path + project + "/" + workflow)
#     wf_task_names = [t["name"] for t in wf_tasks]
#     for t in wf_task_names:
#         wf_tasks["status"] = "new"
#         task_path = path + "/" + t
#         if "pid" in os.listdir(task_path):
#             logging.info(datetime.datetime.now().isoformat() + ": WARNING: pid file still exists in" + str(t))
#             os.remove(task_path + "/pid")
#     with open(path+"/workflow.json", "w") as fp:
#         json.dump(wf_tasks, fp, indent=3)

def run_task(task_name):
    new_task = RunningTask(task_name)
    new_task.run()
    running_tasks.add(new_task)
    if new_task.task_json()["task"]["exec"] == "await":
        status = new_task.wait_not_parallel()
        # if "error" in status: #and not terminate_flag:
        #     new_task.rerun()
        #     running_tasks.add(new_task)
        #     new_task.wait_not_parallel()
        return None
    else:
        logging.info(datetime.datetime.now().isoformat() + ": running in parallel")
        return new_task


def stop_all_tasks():
    global running_tasks
    if len(running_tasks) == 0:
        return
    logging.info(datetime.datetime.now().isoformat() + ": KILL!!!")
    logging.info(str([t.task_name for t in running_tasks]))
    for t in running_tasks:
        t.stop_task()
    #running_tasks -= tasks_for_remove
    #tasks_for_remove.clear()
    #logging.info(datetime.datetime.now().isoformat() + ": KILL: Remaine" + str( len(running_tasks)) + "tasks")
    #running_tasks.clear()
    with open(root_path + project + "/" + workflow + "/workflow.json", "r") as wf_json_file:
        wf_tasks = json.load(wf_json_file) # os.listdir("/opt/spa/data/" + project + "/" + workflow)
    wf_task_names = [t["name"] for t in wf_tasks]
    wf_path = root_path + project + "/" + workflow
    for task_dir in wf_task_names:
        if os.path.isdir(os.path.join(wf_path, task_dir)):
            if "pid" in os.listdir(os.path.join(wf_path,task_dir)):
                pid = open(wf_path + "/" + task_dir + "/pid", "r").read()
                logging.info("ERROR: Can't stop unknown process with pid:" + str(pid) + " in folder " + str(task_dir))
    review_statuses()

def kill_all_tasks():
    logging.info(datetime.datetime.now().isoformat() + ": Terminating all tasks")
    global terminate_flag
    terminate_flag = 1
    for t in running_tasks:
        t.process.terminate()
    time.sleep(5)
    for t in running_tasks:
        t.process.poll()

def review_statuses():
    # собрать по всем таскам их текущий статус настоящий, заодно убирая pid файлы умерших - и записать их в json тасков
    #logging.info(datetime.datetime.now().isoformat() + ": INFO: review status")
    global running_tasks
    tasks_for_remove = set()
    for t in running_tasks:
        old_status = t.task_json()["info"]["status"]
        new_status = t.examine_exec_status()
        #logging.info(t + "old:" + old_status + " new:" + new_status)
        if new_status != old_status:
            t.set_json_status(new_status)
        if "error" in new_status and old_status != "rerun" and "error" not in old_status: #and not terminate_flag:
            logging.info(datetime.datetime.now().isoformat() + ": RERUN HERE")
            t.rerun()
        elif new_status != "running" and new_status != "rerun" and new_status != "waiting":
            tasks_for_remove.add(t)
    if len(tasks_for_remove) > 0:
        logging.info(datetime.datetime.now().isoformat() + ": del tasks:"
                     + str([t.task_name for t in tasks_for_remove]))
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
    logging.info(datetime.datetime.now().isoformat() + ": STOP: \n Stopping workflow execution with signal " + str(signum))
    logging.info(datetime.datetime.now().isoformat() + ": frame:" + str(frame))
    global terminate_flag
    terminate_flag = 1


def handler_killer(signum, frame):
    logging.info(datetime.datetime.now().isoformat() + ": STOP: \n Killing workflow execution with signal " + str(signum))
    logging.info(datetime.datetime.now().isoformat() + ": frame:" + str(frame))
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
    logging.basicConfig(filename="/opt/spa/data/"+project + "/" + workflow + "/log",level=logging.DEBUG)
    logging.info(datetime.datetime.now().isoformat() + ": run wf")
    try:
    #if True:

        if "task" in data:
            if run_task(data["task"]) is not None:
                while len(running_tasks) > 0:
                    review_statuses()
                    time.sleep(5)
            #return Success({"answer": stdout})
        else:
            logging.info(datetime.datetime.now().isoformat() + ": run wf")
            clear_wf()
            #resume_wf()
            with open(root_path + project + "/" + workflow + "/workflow.json", "r") as wf_json_file:
                tasks = json.load(wf_json_file)#os.listdir(root_path + project + "/" + workflow)
            task_names = [t["name"] for t in tasks]
            for task in tasks:
                if terminate_flag == 1:
                    logging.info(datetime.datetime.now().isoformat() + ": STOP: Ignoring remaining tasks")
                    break
                run_task(task["name"])
            while len(running_tasks) > 0:
                if terminate_flag == 1:
                    logging.info(datetime.datetime.now().isoformat() + ": STOP: Stopping the workflow execution cycle")
                    stop_all_tasks()
                    break
                review_statuses()
                time.sleep(5)

    except Exception as exc:
        logging.critical(datetime.datetime.now().isoformat() + ": sys exit "+str(exc))
    finally:
        stop_all_tasks()
        review_statuses()
        logging.info(datetime.datetime.now().isoformat() + ": STATUS: workflow is stopped")

