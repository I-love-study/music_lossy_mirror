# 有损压缩同步

## 特点

- 能通过数据库判断文件是否更改，需要重新压缩
- 使用 `qacc` 进行压缩，保证处于较高音质

## 使用方法

1. 从 `Releases` 界面下载压缩包，并解压
   （里面有现成的 qaac 和 python）
2. 打开 `music_sync.py`，更改 `lossless_folder` 和 `lossy_folder` 变量
   （`lossless_folder`为无损存放文件夹，`lossy_folder`是有损压缩后储存的文件夹）
3. 启动 `sync.cmd`
