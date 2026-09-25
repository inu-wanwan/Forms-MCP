"""Google OAuth スコープの定義。

サーバー本体と scripts/get_refresh_token.py の両方がここを参照する。
スコープを増減するときはこのファイルだけを変更し、リフレッシュトークンを取り直すこと。
"""

FORMS_BODY = "https://www.googleapis.com/auth/forms.body"
FORMS_RESPONSES_READONLY = "https://www.googleapis.com/auth/forms.responses.readonly"
DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"

SCOPES: tuple[str, ...] = (FORMS_BODY, FORMS_RESPONSES_READONLY, DRIVE_FILE)

FORMS_MIME_TYPE = "application/vnd.google-apps.form"
