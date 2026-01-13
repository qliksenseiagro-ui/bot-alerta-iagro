import os
import pandas as pd
from telegram import Bot
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# ================= CONFIG =================
BOT_TOKEN = os.environ["BOT_TOKEN"]
PASTA_ALERTAS = "1fFBvjaidKEpHY3VrK_xsi-dcYrNOefAk"
ARQUIVO_NOME = "AlertaIAGRO.xlsx"
ESTADO_ARQUIVO = "estado/ultimo_arquivo.txt"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# =========================================

bot = Bot(token=BOT_TOKEN)


def get_drive_service():
    creds = Credentials.from_service_account_file(
        "service_account.json", scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def get_ultimo_id_processado():
    if not os.path.exists(ESTADO_ARQUIVO):
        return None
    with open(ESTADO_ARQUIVO, "r") as f:
        return f.read().strip() or None


def salvar_ultimo_id(file_id):
    with open(ESTADO_ARQUIVO, "w") as f:
        f.write(file_id)


def get_arquivo_mais_recente(service):
    query = (
        f"'{PASTA_ALERTAS}' in parents and "
        f"name='{ARQUIVO_NOME}' and trashed=false"
    )

    results = service.files().list(
        q=query,
        orderBy="createdTime desc",
        pageSize=1,
        fields="files(id, createdTime)"
    ).execute()

    files = results.get("files", [])
    return files[0] if files else None


def baixar_excel(service, file_id):
    request = service.files().get_media(fileId=file_id)
    with open("alerta.xlsx", "wb") as f:
        f.write(request.execute())


def enviar_alertas():
    service = get_drive_service()
    ultimo_id = get_ultimo_id_processado()

    arquivo = get_arquivo_mais_recente(service)
    if not arquivo:
        print("Nenhum arquivo encontrado.")
        return

    if arquivo["id"] == ultimo_id:
        print("Arquivo já processado.")
        return

    baixar_excel(service, arquivo["id"])

    df = pd.read_excel("alerta.xlsx")

    for _, row in df.iterrows():
        chat_id = str(row["Fone"]).strip()
        texto = str(row["Texto"]).strip()
        bot.send_message(chat_id=chat_id, text=texto)

    salvar_ultimo_id(arquivo["id"])
    print("Alertas enviados com sucesso.")


if __name__ == "__main__":
    enviar_alertas()