FROM maven:3.9-eclipse-temurin-17 AS build

WORKDIR /app

COPY pom.xml .
RUN mvn dependency:go-offline -B

COPY src/ ./src/
RUN mvn clean package -DskipTests -B

FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /app/target/*.jar app.jar

RUN mkdir -p /app/output

ENV JAVA_OPTS=""
ENV OUTPUT_DIR=/app/output

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/status || exit 1

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
