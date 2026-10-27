FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY src/HelloDotnet.csproj .
RUN dotnet restore
COPY src/ .
RUN dotnet publish -c Release -o /out --no-restore

# Chiseled image: no shell, no package manager, runs as non-root by default
FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled
ENV ASPNETCORE_HTTP_PORTS=8080 DOTNET_EnableDiagnostics=0
WORKDIR /app
COPY --from=build /out .
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["dotnet", "HelloDotnet.dll"]
