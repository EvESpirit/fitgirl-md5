# FitGirl Repack MD5 checker (but speed)
A Python script designed to check fitgirl repacks much, much faster than the QuickSFV bundled with her repacks.

GUI Usage:
Download the md5.exe file from this repository's releases.

Run it and point it towards your repack's parent directory.

Terminal usage:
Download the md5.py file from this repository or copy it's source code.

Open CMD or PowerShell in the folder where you put the script and run it with ```python md5.py```

This checker is faster than QuickSFV, but due to the inherent serial nature of MD5, it won't be any quicker if the only archives in the repack is very few but very large files.
If FitGirl happens to read this, use BLAKE3 - it allows for paralellizing the hashing of single files. MD5 sucks.
