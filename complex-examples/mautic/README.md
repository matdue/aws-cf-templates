# Applications
The project contains a MySQL database and Mautic.

URLs:
- Mautic: https://mautic.domain.com/
- Mailpit: https://mailpit.mautic.domain.com/

Each application runs in its own Docker container, hosted on AWS via Fargate. The subdomain is maintained in Route 53. Internet traffic is routed via an Application Load Balancer to the applications. Connection between application and database is realized via Amazon Application Discovery, which technically a DNS entry plus automatic registration.

For MySQL its original Docker image is used. For Mautic its official Docker Image based on Apache is used.

# Mautic
Mautic is installed via the official [Docker Image](https://hub.docker.com/r/mautic/mautic). The Dockerfile is part of a [GitHub repository](https://github.com/mautic/docker-mautic), the Mautic source code is located in another [GitHub repository](https://github.com/mautic/mautic).

## Administrator user
The application does not display a setup page after installation. Instead, the admin user will be installed as defined by environment variables. The initial credentials are:
- Username: administrator
- Password: SomeSecretPassword

The URL will be printed on screen after installation in the cloud: `./run.py setupCloud`

## First installation
The first setup takes about 10 minutes. This delay is caused by a technical limitation as Docker containers running in AWS Fargate are able to use EFS as storage technology only. EFS is quite inefficient regarding small files, and at first start Mautic will copy itself to /var/www/html which is hosted on an EFS drive.

## Persistence
Everything in `/var/www/html` is saved on a separate drive and won't get lost if the application gets restartet.

## Database access
To access the database, perform the following steps:
- Launch an Ubuntu EC2 machine (do not use Amazon Linux as it lacks some necessary MySQL libs), e.g. t4g.nano with ARM architecture
  - Enable SSH access by creating a corresponding Security Group
  - Attach it to VPC `Common VPC`
  - Attach it to Security Group `mautic-MySQL-main-ApplicationAccess...`
  - `ssh ubuntu@111.222.333.444`
- Install MySQL client
  - `sudo apt update`
  - `sudo apt upgrade`
  - `sudo apt install mysql-client`
- Connect to database: `mysql -u mautic -p -h mysqldb.mautic` with password `mauticpwd`
- Connect to Mautic database: `USE mautic;`

## Email server
There is no email server configured, so sending mails is not possible. This includes the password forgotten function.

# MySQL
A MySQL database is set up in a separate Docker container.

# Mailpit
[Mailpit](https://github.com/axllent/mailpit) is an email and SMTP testing tool with API for developers. The web interface is public available and protected with a basic authentication, the mail server is available within the internal network only. Mautic may use this instance as mail server.

## Basic authentication
There is no user management, just a basic authentication with username _administrator_ and password _SomeSecretPassword_.

# Simple local installation
Switch to project directory and run `docker compose up`. Startup of MySQL and Mautic takes about a minute, then the [homepage](http://localhost:8080/) is ready. To stop the application press Ctrl-C.

# Cloud development
## Local setup
1. Install Python 3.10 (or later)
2. Create a virtual environment: `python3 -m venv .venv`
3. Activate virtual environment: `source .venv/bin/activate`
4. Open a terminal and make sure that AWS credentials are ready, i.e. by setting the profile `AWS_PROFILE` or credentials variables `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_DEFAULT_REGION`. The credentials must grant access to Team Data's AWS account.
5. Execute `./setup.sh` to install the required libraries.
6. Execute `./run.py` to show all possible commands, the most important is `setupCloud`. This task will launch the software stack in AWS cloud in a separate environment.

## Separate environment in the cloud
If you would like to make bigger changes and test them before deploying to the final environment, create a Git branch, make your changes, push the branch and create a merge request. A new environment will be launched with a separate database and Mautic instance. Subsequent commits will be deployed to the same environment. When everything is fine, merge your merge request. All changes will be deployed automatically to final environment, and the temporary environment will be shut down.
