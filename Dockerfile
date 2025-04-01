# Stage 1: Build React app
FROM node:18-alpine as build
WORKDIR /app/static
COPY static/package.json static/package-lock.json ./
RUN npm install
COPY static/ .
RUN npm run build

# Stage 2: FastAPI server
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# Copy built React files from the previous stage
COPY --from=build /app/static/build /app/static/build
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
