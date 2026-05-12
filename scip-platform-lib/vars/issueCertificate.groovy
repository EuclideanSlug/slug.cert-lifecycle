/**
 * issueCertificate(app)
 *
 * Issues or renews a certificate for one enrolled application.
 * Accepts a single Map representing one entry from a PTx-<env>-certs.yml catalogue file.
 *
 * Assumes jagent-ec2-role in the target spoke account, writes a non-secret Ansible vars
 * file, invokes the universal-vault-cert-issuer role, then removes the vars file.
 */
def call(Map app) {
    _validateApp(app)

    String accountId   = app.deployment.account_id
    String accountName = app.deployment.account_name
    String secretName  = "/scip/certs/${app.name}"
    String varsFile    = "${env.WORKSPACE}/.cert-vars-${app.name}-${currentBuild.number}.json"

    echo "issueCertificate: app=${app.name} account=${accountName} (${accountId})"

    try {
        writeFile file: varsFile, text: _toJson(_buildVarsMap(app, secretName))

        withAWS(role: 'jagent-ec2-role', roleAccount: accountId, region: 'eu-west-2') {
            withEnv(["ANSIBLE_ROLES_PATH=${env.WORKSPACE}/scip/cert-lifecycle/ansible/roles"]) {
                sh(script: """
                    set +x
                    ansible-playbook scip/cert-lifecycle/ansible/playbooks/issue-certificate.yml \\
                        --extra-vars @${varsFile}
                """)
            }
        }
    } finally {
        sh "rm -f ${varsFile}"
    }
}

private void _validateApp(Map app) {
    if (app == null) {
        error('issueCertificate: app argument must not be null')
    }

    for (String field : ['name', 'common_name', 'ttl', 'deployment']) {
        if (!app.get(field)) {
            error("issueCertificate: missing required field '${field}'")
        }
    }

    Map dep = app.deployment as Map

    for (String field : ['type', 'account_id', 'account_name']) {
        if (!dep.get(field)) {
            error("issueCertificate: missing required deployment.${field} in app '${app.name}'")
        }
    }

    if (!['ec2', 'ecs'].contains(dep.type)) {
        error("issueCertificate: invalid deployment.type '${dep.type}' for app '${app.name}'. Must be 'ec2' or 'ecs'")
    }

    if (!app.name.endsWith("-${dep.account_name}")) {
        error("issueCertificate: app name '${app.name}' must end with '-${dep.account_name}'")
    }

    if (dep.type == 'ecs') {
        for (String field : ['cluster', 'service']) {
            if (!dep.get(field)) {
                error("issueCertificate: ECS app '${app.name}' is missing deployment.${field}")
            }
        }
    }
}

@NonCPS
private Map _buildVarsMap(Map app, String secretName) {
    Map vars = [
        app_name:        app.name,
        common_name:     app.common_name,
        sans:            app.sans ?: [],
        ttl:             app.ttl,
        deployment_type: app.deployment.type,
        account_id:      app.deployment.account_id,
        account_name:    app.deployment.account_name,
        secret_name:     secretName,
        aws_region:      'eu-west-2',
    ]
    if (app.deployment.type == 'ecs') {
        vars.ecs_cluster = app.deployment.cluster
        vars.ecs_service = app.deployment.service
    }
    return vars
}

@NonCPS
private String _toJson(Map vars) {
    groovy.json.JsonOutput.toJson(vars)
}
