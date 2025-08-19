FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o /b3fuzz ./cmd/b3fuzz

FROM ghcr.io/aixcc-finals/base-builder:v1.3.0 AS afl-builder

FROM ghcr.io/aixcc-finals/base-runner:v1.3.0
COPY --from=afl-builder /src/aflplusplus/afl-fuzz /usr/local/bin/afl-fuzz
WORKDIR /app
COPY --from=builder /b3fuzz .

ENV ASAN_OPTIONS="$ASAN_OPTIONS:abort_on_error=1:symbolize=0:detect_odr_violation=0:"
ENV MSAN_OPTIONS="$MSAN_OPTIONS:exit_code=86:symbolize=0"
ENV UBSAN_OPTIONS="$UBSAN_OPTIONS:symbolize=0"
ENV SERVICE_NAME="BandFuzz"

CMD ["./b3fuzz"]
