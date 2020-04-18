

# Django结合websocket和paramiko操作Linux

## 前言

> 怎样优雅的运行Linux命令并实时的显示结果，就像Xshell一样呢？那就要属WebSSH了。
> 基于Web的SSH有很多，基于Python的SSH也有很多，这些都是直接通信，中间没有额外管理。但是以Django为中转桥梁结合websocket和paramiko实现的，网上就很少了。下面是我结合网上参考后的实现图和原理讲解：
## 项目展示
![image-20200418162650671]( https://github.com/wanglu58/webssh/screenshots/image-20200418162650671.png)

![image-20200418162802400](https://github.com/wanglu58/webssh/screenshots/image-20200418162802400.png)

![image-20200418163237539](https://github.com/wanglu58/webssh/screenshots/image-20200418163237539.png)



##  **所需技术**

- websocket 目前市面上大多数的 webssh 都是基于 websocket 协议完成的
- django-channels django 的第三方插件, 为 django 提供 websocket 支持
- xterm.js 前端模拟 shell 终端的一个库
- paramiko python 下对 ssh2 封装的一个库



##  如何将所需技术整合起来

1. xterm.js 在浏览器端模拟 shell 终端, 监听用户输入通过 websocket 将用户输入的内容上传到 django
2. django 接受到用户上传的内容, 将用户在前端页面输入的内容通过 paramiko 建立的 ssh 通道上传到远程服务器执行
3. paramiko 将远程服务器的处理结果返回给 django
4. django 将 paramiko 返回的结果通过 websocket 返回给用户
5. xterm.js 接收 django 返回的数据并将其写入前端页面
6.  lrzsz  基于zmodem协议实现的文件传输



## 流程图

 ![img](https://github.com/wanglu58/webssh/screenshots/0.png) 

 整个数据流：用户打开浏览器--》浏览器发送websocket请求给Django建立长连接--》Django与要操作的服务器建立SSH通道，实时的将收到的用户数据发送给SSH后的主机，并将主机执行的结果数据返回给浏览器 

 操作物理机或者虚拟机的时候我们可以使用`Paramiko`模块来建立SSH长连接隧道，`Paramiko`模块建立SSH长连接通道的方法如下： 

```
# 实例化SSHClient
ssh_client = paramiko.SSHClient()
# 当远程服务器没有本地主机的密钥时自动添加到本地，这样不用在建立连接的时候输入yes或no进行确认
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
# 用key进行认证
if ssh_key:
	pass
else:
    # 用账号密码的方式进行认证
    ssh_client.connect(username=user, password=password, hostname=host, port=port, timeout=timeout)

# 打开ssh通道，建立长连接
transport = ssh_client.get_transport()
self.channel = transport.open_session()
# 获取ssh通道，并设置term和终端大小
self.channel.get_pty(term=term, width=pty_width, height=pty_height)
# 激活终端，正常登陆
self.channel.invoke_shell()
# 一开始展示Linux欢迎相关内容,后面不进入此方法
for i in range(2):
    recv = self.channel.recv(1024).decode('utf-8')
    self.message['status'] = 0
    self.message['message'] = recv
    message = json.dumps(self.message)
    self.websocker.send(message)
    self.res += recv

# 创建3个线程将服务器返回的数据发送到django websocket（1个线程都可以）
Thread(target=self.websocket_to_django).start()
# Thread(target=self.websocket_to_django).start()
# Thread(target=self.websocket_to_django).start()
```



 连接建立，可以通过如下方法给SSH通道接收数据和发送数据：

```
self.channel.recv(nbytes)
self.channel.send(data)
```



 当然SSH返回的数据也可以通过如下方法持续的输出给Websocket：

```
while not self.channel.exit_status_ready():
   	data = self.channel.recv(40960)
   	if not len(data):
   		return

    # SSH返回的数据需要转码为utf-8，否则json序列化会失败
    data = data.decode('utf-8')
    self.message['status'] = 0
    self.message['message'] = data
    self.res += data
    message = json.dumps(self.message)
    self.websocker.send(message)
```

 

 有了这些信息，实现WebSSH浏览器操作物理机或者虚拟机就不算困难了。

## WebSSH动态调整终端窗口大小

 如果我中途调整了浏览器的大小，显示就乱了，这该怎么办？ 好办， 终端窗口的大小需要浏览器和后端返回的Terminal大小保持一致，单单调整页面窗口大小或者后端返回的Terminal窗口大小都是不行的，那么从这两个方向来说明该如何动态调整窗口的大小 。

 首先`Paramiko`模块建立的SSH通道可以通过`resize_pty`来动态改变返回Terminal窗口的大小，使用方法如下： 

```
def resize_pty(self, cols, rows):
    self.ssh_channel.resize_pty(width=cols, height=rows)
```

然后Django的Channels每次接收到前端发过来的数据时，判断一下窗口是否有变化，如果有变化则调用上边的方法动态改变Terminal输出窗口的大小

我在实现时会给传过来的数据加个status，如果status不是0，则调用resize_pty的方法动态调整窗口大小，否则就正常调用执行命令的方法，代码如下：

```
def receive(self, text_data=None, bytes_data=None):
    if text_data is None:
        self.ssh.django_bytes_to_ssh(bytes_data)
    else:
        data = json.loads(text_data)
        if type(data) == dict:
            status = data['status']
            if status == 0:
                data = data['data']

                self.ssh.shell(data)
            else:
                cols = data['cols']
                rows = data['rows']
                self.ssh.resize_pty(cols=cols, rows=rows)
```

## WebSSH通过lrzsz上传下载文件

当使用Xshell或者SecureCRT终端工具时，我的所有文件传输工作都是通过`lrzsz`来完成的，主要是因为其简单方便，不需要额外打开sftp之类的工具，通过命令就可轻松搞定，在用了WebSSH之后一直在想，这么便捷的操作WebSSH能够实现吗？

答案是肯定的，能实现！这要感谢这个古老的文件传输协议：`zmodem`

zmodem采用串流的方式传输文件，是xmodem和ymodem协议的改良进化版，具有传输速度快，支持断点续传、支持完整性校验等优点，成为目前最流行的文件传输协议之一，也被众多终端所支持，例如Xshell、SecureCRT、item2等

优点之外，zmodem也有一定的局限性，其中之一便是只能可靠地传输大小**不超过4GB**的文件，但对于大部分场景下已够用，超大文件的传输一般也会寻求其他的传输方式

lrzsz就是基于zmodem协议实现的文件传输，linux下使用非常方便，只需要一个简单的命令就可以安装，例如centos系统安装方式如下：

```
yum install lrzsz
```

安装完成后就可以通过`rz`命令上传文件，或者`sz`命令下载文件了，这么说上传或下载其实不是很准确，在zmodem协议中，使用receive接收和send发送来解释更为准确，无论是receive还是send都是由**服务端来发起**的

`rz`的意思为recevie zmodem，服务端来接收数据，对于客户端来说就是上传

`sz`的意思是send zmodem，服务端来发送数据，对于客户端来说就是下载

文件的传输需要服务端和客户端都支持zmodem协议，服务端通过安装lrzsz实现了对zmodem协议的支持，Xshell和SecureCRT也支持zmodem协议，所以他们能通过rz或sz命令实现文件的上传和下载，那么Web浏览器要如何支持zmodem协议呢？

我们所使用的终端工具xterm.js在3.x版本提供过zmodem扩展插件， 但很可惜 xterm v4 版本后去掉了 zmodem 插件，只能直接使用 zmodem.js 实现，但是不知道什么原因，登陆 webssh 后，第一次输出命令回车后会卡顿一下才出数据，v3.14.5 就不会卡顿，v3.14.5还可以也可以直接使用 zmodem.js，所以这里使用 v3.14.5，终端功能方面v3 和 v4 我没发现有什么多大的差别。zmodem调用系统rzsz命令实现文件上传下载了

需要注意的是zmodem是个二进制协议，只支持二进制流，所以通过websocket传输的数据必须是二进制的，在django的channel中可以通过指定发送消息的类型为`bytes_data`来实现websocket传输二进制数据，这是后端实现的核心：

```
websocket.send(bytes_data=data)
```

又深入研究了zmodem协议是如何实现识别的，发现了zmodem的实现原理

在服务器上执行sz命令后，会先输出`b'**\x18B0800000000022d\r\x8a'`这样的内容，标识文件下载开始，当文件下载结束后会输出`b'OO'`，取这两个特殊标记之间的二进制流组合成文件，就是要下载的完整文件

rz命令类似，会在开始时输出`b'rz waiting to receive.**\x18B0100000023be50\r\x8a'`标记， 知道了这个规则， 就好区分用户上传和下载文件了：

```
while not self.channel.exit_status_ready():
    if self.zmodemOO:
        # 文件开始下载
        self.zmodemOO = False
        data = self.channel.recv(2)
        if not len(data):
            return
        # 文件下载结束
        if data == b'OO':
            self.websocker.send(bytes_data=data)
            continue
        else:
            data = data + self.channel.recv(40960)
    else:
        data = self.channel.recv(40960)
        if not len(data):
            return

    if self.zmodem:
        if zmodemszend in data or zmodemrzend in data:
            self.zmodem = False
            if zmodemszend in data:
                self.zmodemOO = True
        if zmodemcancel in data:
            self.zmodem = False
        self.websocker.send(bytes_data=data)
    else:
        if zmodemszstart in data or zmodemrzstart in data:
            self.zmodem = True
            self.websocker.send(bytes_data=data)
        else:
            # SSH返回的数据需要转码为utf-8，否则json序列化会失败
            data = data.decode('utf-8')
            self.message['status'] = 0
            self.message['message'] = data
            self.res += data
            message = json.dumps(self.message)
            self.websocker.send(message)
        except:
            self.close()
```

## 总结

完整代码，我已经放到Github上了，忘记了可以参考！

