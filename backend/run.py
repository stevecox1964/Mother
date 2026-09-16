import os
from waitress import serve
from mother.app import create_app

if __name__ == "__main__":
    port = int(os.environ.get("MOTHER_PORT", "5010"))
    print(f"Mother is listening at http://127.0.0.1:{port}", flush=True)
    serve(create_app(start_search_worker=True), host="127.0.0.1", port=port, threads=8)
