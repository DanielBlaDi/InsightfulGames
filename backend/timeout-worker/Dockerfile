FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
COPY . .
RUN chmod +x gradlew && ./gradlew bootJar --no-daemon

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/build/libs/timeout-worker.jar app.jar
COPY --chmod=755 docker/timeout-worker /app/timeout-worker
# Puerto de la ficha técnica (contrato, 18.1). El valor real lo fija la variable PORT.
EXPOSE 8088
ENTRYPOINT ["/app/timeout-worker"]
