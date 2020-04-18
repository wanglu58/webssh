from django.test import TestCase

# Create your tests here.

import paramiko

def main():
    sshClient = paramiko.SSHClient()
    sshClient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sshClient.connect(hostname = "localhost", port = 22, username = "root", password = "password")

    stdin, stdout, stderr= sshClient.exec_command('df -h ')# stdout 为正确输出，stderr为错误输出，同时是有1个变量有值
    print(stdout.read().decode('utf-8'))

    sshClient.close()


if __name__ == '__main__':
    main()