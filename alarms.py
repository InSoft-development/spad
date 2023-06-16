import signal
import time
from datetime import datetime
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

client = clickhouse_connect.get_client(host='10.23.0.177', username='default', password='asdf')

header_a = "N Float64, potential Float64, KrP Int, P Float64, anomaly_time Nullable(Float64)," \
        "KrT Int, anomaly_date Nullable(DateTime64(3,\'Europe/Moscow\')), timestamp DateTime64(3,\'Europe/Moscow\')," \
        "model_timestamp DateTime64(3,\'Europe/Moscow\')"
client.command("DROP TABLE IF EXISTS slices_play_multic")
sql = "CREATE TABLE slices_play_multic (" + header_a + ") ENGINE = " \
      "MergeTree() PARTITION BY toYYYYMM(timestamp) ORDER BY (timestamp) PRIMARY KEY (timestamp)"
print(sql, "\n\n")
client.command(sql)

client.command("DROP TABLE IF EXISTS alarms_multic")
sql = "CREATE TABLE alarms_multic (timestamp DateTime64(3,\'Europe/Moscow\'), alarm String, skipped Bool) ENGINE = " \
      "MergeTree() PARTITION BY toYYYYMM(timestamp) ORDER BY (timestamp) PRIMARY KEY (timestamp)"
print(sql, "\n\n")
client.command(sql)

KrP_anomaly_active = False
KrT_anomaly_active = False
while not terminate_flag:
        row = client.query_df("SELECT * FROM slices_play WHERE timestamp > subtractSeconds(now(),5) order by timestamp desc limit 1")[0]
        if row["KrP"] == 1:
            if not KrP_anomaly_active:
                KrP_anomaly_active = True
                kks = d.drop("timestamp",axis=1).idxmax(axis=1)[0]
                data = "Превышение уровня аномальности на протяжении 6 часов, потенциальная причина датчик " + kks
                print(data)
                d = pd.DataFrame([{"timestamp": t, "alarm": data, "skipped":False}])
                client.insert_df('alarms_multic', d)
        else:
            KrP_anomaly_active = False

        if row["KrT"] == 1:
            if not KrT_anomaly_active:
                KrT_anomaly_active = True
                kks = d.drop("timestamp",axis=1).idxmax(axis=1)[0]
                data = "Прогнозное время до аномалии меньше 720 часов, потенциальная причина датчик  " + kks
                print(data)
                d = pd.DataFrame([{"timestamp": t, "alarm": data, "skipped":False}])
                client.insert_df('alarms_multic', d)
        else:
            KrT_anomaly_active = False
        if terminate_flag:
            break
        else:
            time.sleep(0.01)
        print(index)
