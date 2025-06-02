# FitGirl Repack MD5 checker (but speed)
A Python script designed to check fitgirl repacks much, much faster than the QuickSFV bundled with her repacks.

Usage:
Download the md5.py file from this repository and place it in the MD5 folder of any FitGirl repack.

Open CMD or PowerShell in this folder and run it with ```python md5.py```

This checker is faster than QuickSFV, but due to the inherent serial nature of MD5, it won't be any quicker if the only archives in the repack is very few but very large files.
If FitGirl happens to read this, use BLAKE3 - it allows for paralellizing the hashing of single files. MD5 sucks.
