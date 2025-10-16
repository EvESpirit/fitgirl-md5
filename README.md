# FitGirl Repack MD5 checker (but speed)
A Python script designed to check fitgirl repacks much, much faster than the QuickSFV bundled with her repacks.




### GUI Usage:
Download the md5.exe file from this repository's releases.

>*(Optional) Verify with a free tool like File Hasher (available on the Microsoft Store) or using PowerShell's inbuilt ```Get-FileHash md5.exe``` capabilities.*

```SHA256 for the 1.0 release: 3D847A91ABC398A512E1636AE804DD90A097C900364C5A65270351F5AB69DC18```

```SHA256 for the 1.1 release: 15325A59F27475984925CA306DC431501BEC8A129505EE04BFBA6578FBF76852```

Run it and point it towards your repack's parent directory.





### Terminal usage:
Download the md5.py file from this repository or copy it's source code.

Open CMD or PowerShell in the folder where you put the script and run it with ```python md5.py```




## This checker is faster than QuickSFV, but due to the inherent serial nature of MD5, it won't be any quicker if the only archives in the repack is very few but very large files.
If FitGirl happens to read this, use BLAKE3 - it allows for paralellizing the hashing of single files. MD5 sucks.
