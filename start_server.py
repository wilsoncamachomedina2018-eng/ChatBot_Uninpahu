import os

port = int(os.environ.get("PORT", 10000))

app.run(host="0.0.0.0", port=port)