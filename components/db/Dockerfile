FROM postgres:13-alpine

COPY schema.sql /schema.sql

CMD ["sh", "-c", "psql \"$DATABASE_URL\" -f /schema.sql"]