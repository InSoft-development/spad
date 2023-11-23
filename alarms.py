import signal
import time
from datetime import datetime,timedelta
import pandas as pd
import clickhouse_connect

terminate_flag = False


def handler_stop(signum, frame):
    global terminate_flag
    terminate_flag = True


# soft stop at next cycle iteration
signal.signal(signal.SIGTERM, handler_stop)
signal.signal(signal.SIGINT, handler_stop)

t = datetime.now()
print("data read")

client = clickhouse_connect.get_client(host='10.23.0.87', username='default', password='asdf')
kks_df = client.query_df("SELECT * from kks")
groups = set(kks_df["group"].astype(int)) - set([0])
print(groups)

header_p = ""
for g in groups:
    header_p += "anomaly_time"+str(g)+" Nullable(Float64)," \
        "anomaly_date"+str(g)+" Nullable(DateTime64(3,\'Europe/Moscow\'))," \
        "P"+str(g)+" Float64, "
header_p += "timestamp DateTime64(3,\'Europe/Moscow\')"
client.command("DROP TABLE IF EXISTS sum_p")
sql = "CREATE TABLE sum_p (" + header_p + ") ENGINE = " \
      "MergeTree() PARTITION BY toYYYYMM(timestamp) ORDER BY (timestamp) PRIMARY KEY (timestamp)"
print(sql, "\n\n")
client.command(sql)

client.command("DROP TABLE IF EXISTS alarms")
sql = "CREATE TABLE alarms (alarm String, group Int, skipped Bool, timestamp DateTime64(3,\'Europe/Moscow\')) ENGINE = " \
      "MergeTree() PARTITION BY toYYYYMM(timestamp) ORDER BY (timestamp) PRIMARY KEY (timestamp)"
print(sql, "\n\n")
client.command(sql)

while not terminate_flag:
    sum_p = pd.DataFrame()
    alarms = pd.DataFrame()
    for g in groups:
        lstm = client.query_df("SELECT prob,count, timestamp FROM lstm_group"+str(g)+" order by timestamp desc limit 1")
        print("LSTM:\n", lstm)

        pot = client.query_df("SELECT probability,anomaly_time, timestamp FROM potential_predict_"+str(g)+" order by timestamp desc limit 1")
        print("Potential:\n", pot)

        P = max(lstm["prob"][0], pot["probability"][0])
        if pot["anomaly_time"][0] == "NaN":
            anomaly_time = lstm["count"][0]
        else:
            anomaly_time = min(lstm["count"][0], int(pot["anomaly_time"][0]))
        anomaly_date = datetime.now() + timedelta(hours=anomaly_time)
        t = max(pot["timestamp"][0],lstm["timestamp"][0])
        sum_p["anomaly_time"+str(g)] = [anomaly_time]
        sum_p["anomaly_date"+str(g)] = [anomaly_date]
        sum_p["P"+str(g)] = P

        if P > 95:
            data = "Превышение уровня аномальности, gr=" + str(g)
            print(data)
            d = pd.DataFrame([{"timestamp": t, "alarm": data, "group": g, "skipped": False}])
            client.insert_df('alarms', d)

        if anomaly_time < 720:
            data = "Прогнозное время до аномалии меньше 720 часов, gr=" + str(g)
            print(data)
            d = pd.DataFrame([{"timestamp": t, "alarm": data, "group": g, "skipped": False}])
            client.insert_df('alarms', d)
    print(sum_p)
    client.insert_df('sum_p', sum_p)
    if terminate_flag:
        break
    else:
        time.sleep(5)
