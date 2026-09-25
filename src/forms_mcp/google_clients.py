"""Forms API v1 / Drive API v3 の service オブジェクトを作る。

googleapiclient の service（内部の httplib2.Http）はスレッドセーフではない。
ツールは同期関数として SDK のワーカースレッドで実行されるため、呼び出しごとに service を作る。
discovery ドキュメントはライブラリ同梱のものを使うので、作成時にネットワークアクセスは発生しない。
"""

from __future__ import annotations

from typing import Any, Protocol

from googleapiclient.discovery import build

from forms_mcp.auth import CredentialsProvider


class GoogleServices(Protocol):
    def forms(self) -> Any: ...

    def drive(self) -> Any: ...


class DefaultGoogleServices:
    def __init__(self, provider: CredentialsProvider) -> None:
        self._provider = provider

    def forms(self) -> Any:
        return build("forms", "v1", credentials=self._provider.get_credentials(), cache_discovery=False)

    def drive(self) -> Any:
        return build("drive", "v3", credentials=self._provider.get_credentials(), cache_discovery=False)
