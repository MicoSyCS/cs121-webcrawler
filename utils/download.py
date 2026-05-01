import requests
import cbor
import time

from utils.response import Response

def download(url, config, logger=None):
    host, port = config.cache_server
    try:
        resp = requests.get(
            f"http://{host}:{port}/",
            params=[("q", f"{url}"), ("u", f"{config.user_agent}")],
            timeout=60)
    except requests.exceptions.RequestException as e:
        logger.error(f"Download error for {url}: {e}")
        return Response({"error": str(e), "status": 0, "url": url})
    try:
        if resp and resp.content:
            return Response(cbor.loads(resp.content))
    except (EOFError, ValueError) as e:
        pass
    logger.error(f"Spacetime Response error {resp} with url {url}.")
    return Response({
        "error": f"Spacetime Response error {resp} with url {url}.",
        "status": resp.status_code,
        "url": url})
