@Library('scip-platform-lib') _

pipeline {
    // prod runs on the prod shared-services Jenkins agent; all other environments use preprod.
    agent { label params.ENVIRONMENT == 'prod' ? 'prodc' : 'preprod' }

    parameters {
        choice(
            name: 'PRODUCT_TEAM',
            choices: ['PT2', 'PT3', 'PT4', 'PT5'],
            description: 'Product team certificate catalogue to use'
        )
        choice(
            name: 'ENVIRONMENT',
            choices: ['dev', 'test', 'preprod', 'prod'],
            description: 'Environment certificate catalogue to use'
        )
        string(
            name: 'APP_NAME',
            defaultValue: '',
            description: 'Optional. If set, only this app is issued/renewed. If empty, all apps in the catalogue are processed sequentially.'
        )
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Issue certificate(s)') {
            steps {
                script {
                    String cataloguePath = "scip/cert-lifecycle/certs/${params.PRODUCT_TEAM}-${params.ENVIRONMENT}-certs.yml"
                    echo "Catalogue: ${cataloguePath}"

                    def catalogue = readYaml file: cataloguePath

                    if (!catalogue.apps || !(catalogue.apps instanceof List) || catalogue.apps.size() == 0) {
                        error("${cataloguePath} does not contain a valid top-level 'apps' list")
                    }

                    // Collect names and detect duplicates without closures
                    List names = []
                    for (int i = 0; i < catalogue.apps.size(); i++) {
                        names.add(catalogue.apps[i].name)
                    }

                    Set seen = new HashSet()
                    List dupes = []
                    for (int i = 0; i < names.size(); i++) {
                        if (!seen.add(names[i]) && !dupes.contains(names[i])) {
                            dupes.add(names[i])
                        }
                    }
                    if (dupes.size() > 0) {
                        error("Duplicate app names found in ${cataloguePath}: ${dupes.join(', ')}")
                    }

                    // Resolve which apps to process
                    List appsToProcess = []
                    String appNameFilter = params.APP_NAME?.trim()

                    if (appNameFilter) {
                        for (int i = 0; i < catalogue.apps.size(); i++) {
                            if (catalogue.apps[i].name == appNameFilter) {
                                appsToProcess.add(catalogue.apps[i])
                            }
                        }
                        if (appsToProcess.size() == 0) {
                            error("APP_NAME '${appNameFilter}' not found in ${cataloguePath}. Available apps: ${names.join(', ')}")
                        }
                    } else {
                        for (int i = 0; i < catalogue.apps.size(); i++) {
                            appsToProcess.add(catalogue.apps[i])
                        }
                    }

                    // Issue certificates sequentially — fail fast on first error
                    for (int i = 0; i < appsToProcess.size(); i++) {
                        def app = appsToProcess[i]
                        echo "Processing app ${i + 1} of ${appsToProcess.size()}: ${app.name}"
                        try {
                            issueCertificate(app)
                        } catch (Exception e) {
                            error("Certificate issuance failed for app '${app.name}': ${e.message}")
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            cleanWs()
        }
    }
}
