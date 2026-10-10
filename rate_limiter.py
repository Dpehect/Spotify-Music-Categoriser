import os
import time
import requests
from typing import Optional, Dict, Any

class SpotifyRateLimiter:
    """
    Dayanıklı Rate Limit (429) & Hata Koruyucusu (Circuit Breaker & Exponential Backoff):
    - Spotify yanıtında 429 gelirse 'Retry-After' başlığını okur.
    - Geçici 5xx hatalarında sınırlı üstel geri çekilme uygular.
    - 400, 401, 403 gibi kesin hatalarda anında durur (gereksiz retry yapmaz).
    - Basit devre kesici (Circuit Breaker) ile art arda 5 kez çöken uç noktaları geçici olarak bekletir.
    """
    def __init__(self, max_retries: int = 3, base_backoff: float = 1.0, timeout: float = 5.0):
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.timeout = timeout
        self.consecutive_failures = 0
        self.circuit_open_until = 0.0

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        # Devre kesici kontrolü
        now = time.time()
        if now < self.circuit_open_until:
            raise requests.exceptions.RequestException(f"Circuit breaker açık: {url} geçici olarak askıya alındı.")

        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        retries = 0
        backoff = self.base_backoff

        while retries <= self.max_retries:
            try:
                response = requests.request(method, url, **kwargs)
            except requests.exceptions.Timeout:
                retries += 1
                if retries > self.max_retries:
                    self._record_failure()
                    raise
                time.sleep(backoff)
                backoff *= 1.5
                continue
            except requests.exceptions.RequestException as e:
                self._record_failure()
                raise e

            if response.status_code == 429:
                self._record_failure()
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait_time = int(retry_after) + 0.5
                else:
                    wait_time = backoff

                time.sleep(min(wait_time, 15.0)) # Maksimum 15 saniye beklet
                retries += 1
                backoff *= 2
                continue

            # 5xx sunucu hataları için sınırlı retry
            if 500 <= response.status_code < 600:
                self._record_failure()
                retries += 1
                if retries <= self.max_retries:
                    time.sleep(backoff)
                    backoff *= 1.5
                    continue
                return response

            # 2xx veya 4xx (400, 401, 403, 404) için retry yapılmaz, doğrudan dönülür
            self.consecutive_failures = 0
            return response

        return response

    def _record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= 5:
            # 5 ardışık hatada devreyi 30 saniye aç
            self.circuit_open_until = time.time() + 30.0
