# CRS-SLICE

## How to run on CRS
Four environment variables need to be passed into container:
```bash
RABBITMQ_URL
DATABASE_URL
SLICE_TASK_QUEUE='slice-task'
STORAGE_DIR
```
One directory need to be passed into container to collect slice output:
```bash
<CRS_STORAGE_DIR_OUT>:<STORAGE_DIR>
```

## How to run on local
```bash
time bash -c 'docker save gcr.io/oss-fuzz-base/base-builder:latest | gzip > base-builder.tar.gz'
# On Jupiter(/storage):
# -rw-rw-r--  1 user user 3.1G Feb 17 02:26 base-builder.tar.gz
# real    4m22.040s
# user    3m27.433s
# sys     0m13.659s
time docker build -t crs-slice .
# On Jupiter:
# real    3m55.258s
# user    0m6.808s
# sys     0m10.894s
docker run -it --rm --privileged -e RABBITMQ_URL=<RABBITMQ_URL> -e DATABASE_URL=<DATABASE_URL> -e SLICE_TASK_QUEUE='slice-task' -e STORAGE_DIR=<CRS_STORAGE_DIR> -v <CRS_STORAGE_DIR_OUT>:<CRS_STORAGE_DIR_IN> crs-slice
# [Mon Feb 17 03:05:14 UTC 2025] [INFO] [/usr/local/bin/entrypoint.sh] [AIxCC] loading base-builder image and removing tar
# Loaded image: gcr.io/oss-fuzz-base/base-builder:latest
# ...
# [Mon Feb 17 03:08:05 UTC 2025] [INFO] [/usr/local/bin/entrypoint.sh] [AIxCC] running main.py
```

## Sample Message
```python
SliceMsg(task_id='1', 
        is_sarif=True, 
        slice_id='1', 
        project_name='libpng', 
        focus='example-libpng', 
        repo=['/storage/zijun_data/crs-slice/tests/libpng/example-libpng.tar.gz'], 
        fuzzing_tooling='/storage/zijun_data/crs-slice/tests/libpng/fuzz-tooling.tar.gz', 
        diff='/storage/zijun_data/crs-slice/tests/libpng/diff.tar.gz', 
        slice_target=[['contrib/tools/pngfix.c', 'OSS_FUZZ_process_zTXt_iCCP'], ['contrib/tools/pngfix.c', 'OSS_FUZZ_zlib_check'], ['pngrtran.c', 'OSS_FUZZ_png_init_read_transformations'], ['pngrtran.c', 'OSS_FUZZ_png_do_read_invert_alpha'], ['pngrtran.c', 'OSS_FUZZ_png_do_read_filler'], ['pngrutil.c', 'OSS_FUZZ_png_check_chunk_length']])
```

## TODO List
- support delta mode
- add line number slice support