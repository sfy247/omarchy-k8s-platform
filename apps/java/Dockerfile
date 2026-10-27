FROM eclipse-temurin:25-jdk AS build
WORKDIR /src
COPY src/Hello.java .
RUN javac -d /out Hello.java

FROM eclipse-temurin:25-jre
ENV PORT=8080 JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75"
WORKDIR /app
COPY --from=build /out .
USER 10001:10001
EXPOSE 8080
CMD ["java", "-cp", "/app", "Hello"]
