# Google Forms MCP サーバー

claude.ai の「カスタムコネクタ」から Google フォームを作成・編集・参照するためのリモート MCP サーバーです。
Google Forms API v1 の全メソッドをツール化し、Forms API にない操作（一覧・複製・ゴミ箱移動）は Drive API v3 で補います。

- Python 3.12 / 公式 MCP Python SDK v2（`MCPServer`）/ Streamable HTTP（stateless・JSON レスポンス）
- `google-api-python-client` + `google-auth`
- ホスト: Render Web Service

## ツール一覧

| ツール | API | 用途 |
| --- | --- | --- |
| `create_form` | forms.create | フォーム作成（タイトルのみ。`unpublished` で未公開作成も可） |
| `get_form` | forms.get | フォーム全体（items / itemId / index / questionId / revisionId）を取得 |
| `batch_update` | forms.batchUpdate | 質問の追加・変更・削除・移動、説明・設定の変更。writeControl 対応 |
| `set_publish_settings` | forms.setPublishSettings | 公開状態・回答受付の切り替え |
| `get_response` | forms.responses.get | 回答 1 件 |
| `list_responses` | forms.responses.list | 回答一覧（timestamp の filter、ページング） |
| `create_watch` | forms.watches.create | Pub/Sub 通知の watch 作成（SCHEMA / RESPONSES） |
| `list_watches` | forms.watches.list | watch 一覧 |
| `renew_watch` | forms.watches.renew | watch の期限延長（7 日） |
| `delete_watch` | forms.watches.delete | watch 削除 |
| `list_forms` | drive.files.list | フォーム一覧（**このアプリで作成・複製したものだけ**。drive.file の制約） |
| `copy_form` | drive.files.copy | フォーム複製 |
| `trash_form` | drive.files.update | ゴミ箱へ移動（完全削除はしない） |

Google API のエラーは、HTTP ステータス・Google のメッセージ・考えられる原因（スコープ不足、権限なし、updateMask 漏れ、drive.file の範囲外など）を付けてツールのエラーとして返します。

## ディレクトリ構成

```
src/forms_mcp/
  app.py                  # ASGI アプリ / エントリポイント（/healthz と /mcp/<secret> のみ公開）
  server.py               # MCPServer の生成
  config.py               # 環境変数の読み込み
  scopes.py               # OAuth スコープ定数（サーバーとトークン取得スクリプトで共有）
  errors.py               # Google API 実行とエラー整形
  google_clients.py       # Forms / Drive の service 生成
  auth/
    __init__.py           # CredentialsProvider インターフェース
    google_credentials.py # リフレッシュトークン方式（第1段階）
    path_secret.py        # 秘密パスでのディスパッチ、ログのシークレット伏せ字
  tools/                  # forms / responses / watches / drive
scripts/
  get_refresh_token.py    # リフレッシュトークン取得
  check_server.py         # 起動中サーバーの動作確認（ツール一覧 + get_form）
tests/                    # Google API をモックした pytest
```

## 環境変数

| 変数 | 必須 | 説明 |
| --- | --- | --- |
| `MCP_PATH_SECRET` | ○ | MCP エンドポイント `/mcp/<MCP_PATH_SECRET>` の秘密部分（32 文字以上、`/` `?` `#` 不可） |
| `GOOGLE_CLIENT_ID` | ○ | OAuth クライアント ID（デスクトップアプリ） |
| `GOOGLE_CLIENT_SECRET` | ○ | OAuth クライアントシークレット |
| `GOOGLE_REFRESH_TOKEN` | ○ | `scripts/get_refresh_token.py` で取得 |
| `PUBSUB_TOPIC` | | `create_watch` の既定トピック（`projects/<project>/topics/<topic>`） |
| `ALLOWED_HOSTS` | | 追加で許可する Host（カンマ区切り）。localhost と Render の `RENDER_EXTERNAL_HOSTNAME` は自動で許可 |
| `ALLOWED_ORIGINS` | | 追加で許可する Origin（カンマ区切り） |
| `HOST` / `PORT` | | 待ち受けアドレス（既定 `0.0.0.0:8000`。Render では `PORT` が自動設定） |

Google の 3 変数が未設定でもサーバーは起動し、ツール一覧は取得できます（API を呼ぶツールは設定を促すエラーを返します）。

### `MCP_PATH_SECRET` の生成

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# または
openssl rand -hex 32
```

この値を含む URL はパスワードと同じ扱いです。漏れた場合は値を変えて再デプロイし、コネクタを登録し直してください。

## ローカル起動

```sh
uv sync
cp .env.example .env        # MCP_PATH_SECRET と Google の 3 変数を記入
uv run --env-file .env python -m forms_mcp.app
# → http://localhost:8000/healthz が {"status":"ok"} を返す
# → MCP エンドポイント: http://localhost:8000/mcp/<MCP_PATH_SECRET>
```

テスト:

```sh
uv run pytest
```

## リフレッシュトークンの取得

1. Google Cloud コンソール →「API とサービス」→「認証情報」で、作成済みの OAuth クライアント（デスクトップアプリ）の JSON をダウンロードし、プロジェクト直下に置きます（`client_secret*.json` は `.gitignore` 済み）。
2. 次のどちらかを実行します。

   ```sh
   uv run python scripts/get_refresh_token.py --client-secrets client_secret_xxx.json
   # または .env に GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET を書いてから
   uv run --env-file .env python scripts/get_refresh_token.py
   ```

3. ブラウザで Google にログインし、同意画面ではすべての権限にチェックを入れます。
4. ターミナルに表示されたトークンを `GOOGLE_REFRESH_TOKEN` に設定します。3 つのスコープ（forms.body / forms.responses.readonly / drive.file）のどれかが欠けていると警告が出て、終了コード 2 になります。

**注意（トークンの有効期限）:** OAuth 同意画面の User Type が「外部」で公開ステータスが「テスト」のままだと、リフレッシュトークンは **7 日で失効** します。
Google Workspace のアカウントなら User Type を「内部」にし、個人アカウントなら公開ステータスを「本番環境」にしてください（自分だけで使う場合、未確認アプリの警告が出ても続行できます）。
失効すると、ツールは `invalid_grant` を含むエラーを返します。

## MCP Inspector での確認

サーバーをローカルで起動した状態で:

```sh
npx @modelcontextprotocol/inspector
```

ブラウザで開いた Inspector で、次のように設定します。

- Transport Type: **Streamable HTTP**
- URL: `http://localhost:8000/mcp/<MCP_PATH_SECRET>`

「Connect」→「Tools」→「List Tools」で 13 個のツールが表示されます。`get_form` に `form_id` を入れて実行し、結果を確認してください。

コマンドラインだけで確認する場合（Inspector 相当: ツール一覧 + get_form）:

```sh
uv run python scripts/check_server.py http://localhost:8000/mcp/<MCP_PATH_SECRET> --form-id <フォームID>
```

## Render へのデプロイ

1. このディレクトリを GitHub の **private** リポジトリに push します（`.env` やトークンが含まれていないことを `git status` で確認してください）。
2. Render ダッシュボード →「New」→「Blueprint」→ リポジトリを選択します。`render.yaml` が読み込まれます。
3. シークレット扱いの環境変数（`MCP_PATH_SECRET`、`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`GOOGLE_REFRESH_TOKEN`、任意で `PUBSUB_TOPIC`）の値を入力してデプロイします。
4. `https://<サービス名>.onrender.com/healthz` が `{"status":"ok"}` を返すことを確認します。
5. 手元から動作を確認します。

   ```sh
   uv run python scripts/check_server.py https://<サービス名>.onrender.com/mcp/<MCP_PATH_SECRET> --form-id <フォームID>
   ```

補足:

- ビルドは `pip install uv && uv sync --frozen --no-dev`、起動は `.venv/bin/python -m forms_mcp.app` です。依存を変えたら `uv lock` して `uv.lock` もコミットしてください。
- Render の公開ホスト名（`RENDER_EXTERNAL_HOSTNAME`）は自動で許可されます。カスタムドメインを使う場合は `ALLOWED_HOSTS` に追加してください。追加しないと 421 Invalid Host header になります。
- `region` は `render.yaml` で `singapore` にしています。必要に応じて変更してください。

### 無料プランの注意（コールドスタート）

Render の無料プランは、一定時間（約 15 分）アクセスがないとスリープします。次のリクエストで起動し直すまで数十秒〜1 分程度かかるため、**claude.ai からの最初の接続やツール呼び出しがタイムアウトすることがあります**。
その場合は少し待ってから再試行するか、先に `/healthz` を開いて起こしてください。安定して使うなら有料プラン（Starter など）を推奨します。

## claude.ai へのカスタムコネクタ登録

1. claude.ai →「設定」→「コネクタ」→「カスタムコネクタを追加」を開きます（Team / Enterprise では組織のオーナーが組織設定から追加します）。
2. 次のように入力します。
   - 名前: 例「Google Forms」
   - URL: `https://<サービス名>.onrender.com/mcp/<MCP_PATH_SECRET>`
   - 詳細設定の OAuth Client ID / Secret: **空欄**（第1段階では OAuth を使いません）
3. 追加後、チャットの「検索とツール」メニューでコネクタを有効にします。「Google Forms の一覧を見せて」などと依頼して動作を確認してください。

このサーバーは 1 つの Google アカウント（リフレッシュトークンの持ち主）の権限で動きます。コネクタ URL を知っている人は誰でも、そのアカウントとしてフォームを操作できます。URL は共有しないでください。

## watches 用 Pub/Sub の設定メモ

watch を使う場合だけ必要です。OAuth クライアントと同じ Cloud プロジェクトに作るのが簡単です。

```sh
PROJECT=<project-id>
TOPIC=forms-events

gcloud pubsub topics create $TOPIC --project=$PROJECT

# Google Forms の通知用サービスアカウントに Publisher 権限を付与
gcloud pubsub topics add-iam-policy-binding $TOPIC --project=$PROJECT \
  --member="serviceAccount:forms-notifications@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

# 受信用サブスクリプション（pull の例）
gcloud pubsub subscriptions create ${TOPIC}-sub --topic=$TOPIC --project=$PROJECT
```

- 環境変数 `PUBSUB_TOPIC=projects/<project-id>/topics/forms-events` を設定すると、`create_watch` で `topic_name` を省略できます。
- watch は **7 日で失効** します。続ける場合は `renew_watch` で延長してください（定期実行は Cloud Scheduler などで別途用意します）。
- 通知に回答の中身は含まれません（formId と eventType など）。受け取ったら `list_responses`（`filter` に timestamp を指定）で取得します。
- 通知を受けて処理する仕組み（Cloud Run の push サブスクリプションなど）は、このサーバーの範囲外です。

## セキュリティと今後の拡張

- シークレットはログに出しません。アクセスログのパスも `/mcp/***` に伏せます。設定オブジェクトの repr にも値は含まれません。
- `/healthz` と `/mcp/<secret>` 以外はすべて 404 です。シークレットの比較は定数時間で行います。
- MCP SDK の DNS rebinding 対策を有効にし、許可した Host / Origin 以外を拒否します（421 / 403）。
- **将来の OAuth 対応:** 認証は `src/forms_mcp/auth/` に分けてあります。MCP 仕様準拠の OAuth（このサーバーが認可サーバーとなり、裏で Google ログインを仲介）に移るときは、次の 2 点を差し替えます。
  1. `CredentialsProvider` を、リクエストのユーザーに紐づく Google 認証情報を返す実装に替える
  2. `app.py` の `PathSecretDispatcher` を外し、`MCPServer` の `auth` / `auth_server_provider` / `token_verifier` を設定する
