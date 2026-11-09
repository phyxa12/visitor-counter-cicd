pipeline {
    agent any

    environment {
        APP_VERSION  = "1.0.${BUILD_NUMBER}"
        FRONTEND_DIR = "/var/jenkins_home/frontend_live"
    }

    stages {
        stage('Checkout') {
            steps {
                echo "=== [Stage 1/5] Checkout Source Code dari GitHub ==="
                checkout scm
                sh 'git log -1 --pretty=format:"Commit: %h | Author: %an | Message: %s%n"'
            }
        }

        stage('Syntax Check') {
            steps {
                echo "=== [Stage 2/5] Validasi Sintaks Python & Konfigurasi Docker Compose ==="
                sh '''
                    python3 -m py_compile backend/app.py
                    docker compose config -q
                '''
            }
        }

        stage('Build Image') {
            steps {
                echo "=== [Stage 3/5] Build Docker Image Backend (Versi: ${APP_VERSION}) ==="
                sh '''
                    docker compose build --pull
                    docker tag visitor-log-backend:${APP_VERSION} visitor-log-backend:latest
                '''
            }
        }

        stage('Automated Deployment') {
            steps {
                echo "=== [Stage 4/5] Deploy Fullstack Containers via Docker Compose ==="
                sh '''
                    mkdir -p ${FRONTEND_DIR}
                    cp -rf frontend/* ${FRONTEND_DIR}/
                    docker compose up -d --force-recreate --remove-orphans
                    docker compose ps
                '''
            }
        }

        stage('Health Check') {
            steps {
                echo "=== [Stage 5/5] Verifikasi Layanan Backend & Frontend di Network app-net ==="
                sh '''
                    for i in 1 2 3 4 5 6 7 8 9 10; do
                        if docker exec visitor-frontend wget -qO- http://127.0.0.1/api/health | grep -q '"status": "ok"'; then
                            echo "Health check BERHASIL pada percobaan ke-$i!"
                            docker exec visitor-frontend wget -qO- http://127.0.0.1/api/health
                            echo ""
                            docker exec visitor-frontend wget -qO- http://127.0.0.1/api/logs
                            exit 0
                        fi
                        echo "Menunggu service siap (percobaan $i/10)..."
                        sleep 2
                    done
                    echo "Health check GAGAL setelah 10 percobaan!"
                    exit 1
                '''
            }
        }
    }

    post {
        success {
            echo "[SUCCESS] Pipeline CI/CD selesai! Aplikasi aktif di http://localhost:8080 (Build #${BUILD_NUMBER})"
        }
        failure {
            echo "[FAILED] Pipeline CI/CD gagal. Periksa log stage di atas."
        }
        always {
            sh 'docker image prune -f >/dev/null 2>&1 || true'
        }
    }
}
