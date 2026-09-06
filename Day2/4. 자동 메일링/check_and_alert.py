import csv
import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

THRESHOLD = 90.0
CSV_PATH = os.path.join(os.path.dirname(__file__), "process_data.csv")

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]


def find_anomalies(csv_path, threshold):
    anomalies = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if float(row["value"]) >= threshold:
                anomalies.append(row)
    return anomalies


def build_email_body(anomalies, threshold):
    lines = [f"공정 데이터 중 {threshold} 이상 수치가 {len(anomalies)}건 감지되었습니다.\n"]
    for row in anomalies:
        lines.append(
            f"- [{row['timestamp']}] {row['line_id']} / {row['equipment_id']} "
            f"({row['sensor_type']}): {row['value']}{row['unit']}"
        )
    return "\n".join(lines)


def send_email(subject, body, to_addr):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_addr

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)


if __name__ == "__main__":
    anomalies = find_anomalies(CSV_PATH, THRESHOLD)
    if not anomalies:
        print("이상 수치가 없습니다. 메일을 보내지 않습니다.")
    else:
        subject = f"[공정 알림] 임계값({THRESHOLD}) 초과 {len(anomalies)}건 감지"
        body = build_email_body(anomalies, THRESHOLD)
        print("=== 발송 예정 메일 내용 ===")
        print("제목:", subject)
        print(body)
        print("===========================")
        send_email(subject, body, EMAIL_ADDRESS)
        print("메일을 발송했습니다.")
