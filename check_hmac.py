import hmac, hashlib, os, sys

secret = os.environ.get("SERVICENOW_WEBHOOK_SECRET")
if secret is None:
    sys.exit("SERVICENOW_WEBHOOK_SECRET is not an env var in this container; load it the way your settings module does")

body = open("/tmp/body.json", "rb").read()
supplied = sys.argv[1].strip().lower().removeprefix("sha256=")

print("secret length:", len(secret),
      "| leading/trailing whitespace:", secret != secret.strip(),
      "| wrapped in quotes:", secret.startswith(('"', "'")) or secret.endswith(('"', "'")),
      "| non-ASCII:", not secret.isascii())
print("body bytes:", len(body),
      "| ends with newline:", body.endswith(b"\n"),
      "| has BOM:", body.startswith(b"\xef\xbb\xbf"))

def h(k, m):
    return hmac.new(k, m, hashlib.sha256).hexdigest()

cases = {
    "exact":             (secret.encode(), body),
    "body stripped":     (secret.encode(), body.strip()),
    "secret stripped":   (secret.strip().encode(), body),
    "secret unquoted":   (secret.strip().strip("\"'").encode(), body),
}
print("API-side digest (exact):", h(*cases["exact"]))
print("Supplied signature:     ", supplied)
for name, (k, m) in cases.items():
    print(f"{name:16}", "MATCH" if h(k, m) == supplied else "no match")