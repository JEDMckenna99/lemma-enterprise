FROM golang:1.18-alpine AS builder

WORKDIR /app

# Install dependencies
RUN apk add --no-cache git gcc musl-dev

# Copy go.mod first to leverage Docker cache
COPY go.mod ./

# Download dependencies and create go.sum
RUN go mod download
RUN go mod tidy

# Copy the rest of the application
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o oprf-service .

# Use a smaller image for the runtime
FROM alpine:3.16

WORKDIR /app

# Install runtime dependencies
RUN apk add --no-cache ca-certificates tzdata

# Create directory for keys
RUN mkdir -p /app/keys

# Copy the binary from the builder stage
COPY --from=builder /app/oprf-service /app/

# Set default environment variables
ENV PORT=8080
ENV OPRF_KEY_DIR=/app/keys
ENV OPRF_RATE_LIMIT=60
ENV OPRF_ROTATION_DAYS=30
ENV OPRF_METRICS_ENABLED=true
ENV OPRF_DEBUG=false

# Expose the service port - Heroku will override this with its own PORT env var
EXPOSE 8080

# Run the service directly (no shell script)
CMD /app/oprf-service --port=$PORT --keydir=/app/keys 