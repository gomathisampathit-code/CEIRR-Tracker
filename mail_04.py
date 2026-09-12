import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

def send_mail(start_date, end_date, call_pdf, visit_pdf):

    SENDER_EMAIL = "gomathisampath2309@gmail.com" 
    RECEIVER_EMAIL = ["gomathisampath2309@gmail.com",
    "maheshmoorthy@cmcvellore.ac.in",
    "sangeetha.priya@cmcvellore.ac.in",
    "logeshwaran.a@cmcvellore.ac.in",
    "iorv.data@cmcvellore.ac.in",
    "iorv.coordinator@cmcvellore.ac.in",
    "ramit.kundu@cmcvellore.ac.in",
    "ceirr.virology@cmcvellore.ac.in",
    "selvakumarprasad@gmail.com",
    ]
    EMAIL_PASSWORD = "fdhbuegdjjrwtype"

    msg = EmailMessage()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = "CEIRR Screening & COHORT Call and Visit List"

    MESSAGE_ID_FILE = "message_id.txt"

    if os.path.exists(MESSAGE_ID_FILE):
        with open(MESSAGE_ID_FILE, "r") as f:
            original_id = f.read().strip()

        msg["In-Reply-To"] = original_id
        msg["References"] = original_id
    else:
        original_id = make_msgid()
        msg["Message-ID"] = original_id

        with open(MESSAGE_ID_FILE, "w") as f:
            f.write(original_id)

    body = f"""\
Dear Team,

The following participants have upcoming call and visit notifications between {start_date} to {end_date}.

Best regards,
CEIRR Notification Tracker
"""

    msg.set_content(body)

    attachments = [call_pdf, visit_pdf]

    for file_path in attachments:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype="application",
                    subtype="pdf",
                    filename=os.path.basename(file_path)
                )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, EMAIL_PASSWORD)
        smtp.send_message(msg)

    print("Email sent successfully")
