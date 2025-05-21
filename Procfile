web: gunicorn wsgi:app
oprf: cd oprfservice && go build -o oprf-service && ./oprf-service --port=${PORT:-8080} --keydir=./keys
