FROM golang:1.18-alpine AS builder

WORKDIR /app

# Install dependencies
RUN apk add --no-cache git gcc musl-dev

# Copy go.mod and go.sum first to leverage Docker cache
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -a -installsuffix cgo -o oprf-service

# Use a smaller image for the runtime
FROM alpine:3.16

WORKDIR /app

# Install runtime dependencies
RUN apk add --no-cache ca-certificates tzdata

# Copy the binary from the builder stage
COPY --from=builder /app/oprf-service /app/
COPY --from=builder /app/run.sh /app/

# Make run.sh executable
RUN chmod +x /app/run.sh

# Create volume for keys
VOLUME ["/app/keys"]

# Set environment variables for configuration
ENV OPRF_PORT=8080
ENV OPRF_KEY_DIR=/app/keys
ENV OPRF_RATE_LIMIT=60
ENV OPRF_ROTATION_DAYS=30
ENV OPRF_METRICS_ENABLED=true
ENV OPRF_DEBUG=false

# Expose the service port
EXPOSE 8080

# Run the service
ENTRYPOINT ["/app/run.sh"] 