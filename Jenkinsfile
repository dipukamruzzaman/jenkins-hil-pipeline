pipeline {
    agent any

    environment {
        DEVICE_HOST       = 'localhost'
        DEVICE_PORT       = '8766'
        EXPECTED_FIRMWARE = 'fw-2.4.1-release'
        SOAK_MINUTES      = '2'
    }

    triggers {
        pollSCM('H/5 * * * *')
        cron('0 2 * * *')
    }

    stages {

        stage('Setup') {
            steps {
                echo 'Installing dependencies...'
                bat 'pip install -r requirements.txt --break-system-packages'
                bat 'python -m playwright install chromium'
                bat 'if not exist reports mkdir reports'
                echo 'Setup complete.'
            }
        }

        stage('Start Simulator') {
            steps {
                echo 'Starting device simulator...'
                bat '''
                    start /B python app\\device_simulator.py > simulator.log 2>&1
                    timeout /t 3 /nobreak > nul
                '''
                bat 'python -c "import urllib.request; print(urllib.request.urlopen(\'http://localhost:8766/health\').read().decode())"'
                echo 'Simulator running.'
            }
        }

        stage('Parallel Tests') {
            parallel {

                stage('API Tests') {
                    steps {
                        echo 'Running API tests...'
                        bat '''
                            python -m pytest tests/test_api.py ^
                                -v ^
                                --junitxml=reports/api-results.xml ^
                                --html=reports/api-report.html ^
                                --self-contained-html
                        '''
                    }
                    post {
                        always {
                            junit 'reports/api-results.xml'
                        }
                    }
                }

                stage('UI Tests') {
                    steps {
                        echo 'Running UI tests...'
                        bat '''
                            python -m pytest tests/test_ui.py ^
                                -v ^
                                --junitxml=reports/ui-results.xml ^
                                --html=reports/ui-report.html ^
                                --self-contained-html
                        '''
                    }
                    post {
                        always {
                            junit 'reports/ui-results.xml'
                        }
                    }
                }

            }
        }

        stage('HIL Virtualisation') {
            steps {
                echo 'Running HIL virtualisation tests...'
                bat '''
                    python -m pytest tests/test_hil_virtual.py ^
                        -v ^
                        --junitxml=reports/hil-results.xml ^
                        --html=reports/hil-report.html ^
                        --self-contained-html
                '''
            }
            post {
                always {
                    junit 'reports/hil-results.xml'
                }
            }
        }

        stage('Quality Gate') {
            when {
                anyOf {
                    branch 'main'
                    triggeredBy 'TimerTrigger'
                }
            }
            steps {
                script {
                    echo '=========================================='
                    echo 'QUALITY GATE EVALUATION'
                    echo '=========================================='

                    def allPassed = currentBuild.currentResult == 'SUCCESS'

                    if (!allPassed) {
                        echo '┌─────────────────────────────────────────┐'
                        echo '│  TIER 1 — CRITICAL FAILURE              │'
                        echo '│  Hard block — merge not permitted       │'
                        echo '└─────────────────────────────────────────┘'
                        error('QUALITY GATE FAILED — CRITICAL: Test failures detected.')
                    }

                    echo '=========================================='
                    echo 'QUALITY GATE PASSED — all checks green'
                    echo '=========================================='
                }
            }
        }

        stage('Nightly Soak') {
            when {
                triggeredBy 'TimerTrigger'
            }
            environment {
                SOAK_MINUTES = '30'
            }
            steps {
                echo 'Running nightly soak test...'
                bat '''
                    python -m pytest soak/test_soak.py ^
                        -v -s ^
                        --junitxml=reports/soak-results.xml ^
                        --html=reports/soak-report.html ^
                        --self-contained-html
                '''
            }
            post {
                always {
                    junit 'reports/soak-results.xml'
                }
            }
        }

    }

    post {
        always {
            echo 'Stopping device simulator...'
            bat 'taskkill /F /IM python.exe /T 2>nul || echo No python process to kill'
            publishHTML([
                allowMissing:          true,
                alwaysLinkToLastBuild: true,
                keepAll:               true,
                reportDir:             'reports',
                reportFiles:           'api-report.html,ui-report.html,hil-report.html',
                reportName:            'Test Reports'
            ])
            archiveArtifacts(
                artifacts:         'reports/*.xml,reports/*.html,simulator.log',
                allowEmptyArchive: true
            )
        }
        success {
            echo 'All stages passed.'
        }
        failure {
            echo 'Pipeline failed — check test reports above.'
        }
    }
}