# 有损压缩同步

## 特点

- 通过无损文件夹的文件，创建一个有损压缩的文件夹
- 能通过数据库判断源文件是否更改，需要重新压缩
- 使用 `qacc` 进行压缩，保证处于较高音质
- `mp3`, `aac` 等有损格式不进行二次压缩，直接复制
- 使用 `rich` 进行美化，输出美观

## 使用方法（Windows）

注：`qaac` 在 `Linux` 运行需要 `wine`，在这不做介绍

1. 从 `Releases` 界面下载压缩包，并解压
   （里面有现成的 qaac 和 python）
2. 打开 `music_sync.py`，更改 `lossless_folder` 和 `lossy_folder` 变量
   （`lossless_folder`为无损存放文件夹，`lossy_folder`是有损压缩后储存的文件夹）
3. 启动 `sync.cmd`

## 需要改进的地方

- 默认有损库是**不会被其他人更改的**的，假设有损库出现更改，而无损库文件没有被更改的话，则不会重新压缩。
- `qaac` 参数默认为 `-V 127`，假设需要更改则需要直接修改源码
- 无损文件夹名称跟有损文件夹名称修改都需要到源码里面修改
