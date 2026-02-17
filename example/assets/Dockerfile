FROM eclipse-temurin:17-jre-jammy

COPY --from=pet_clinic target/spring-petclinic-rest-*.jar /app.jar

EXPOSE 9966

ENTRYPOINT ["java", "-jar", "/app.jar"]
