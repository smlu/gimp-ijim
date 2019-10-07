# Indiana Jones and The Infernal machine plugin for GIMP
The plugin lets you import and export game's material files (*.mat) in GIMP.
<img src="https://github.com/smlu/gimp-ijim/blob/master/demo/imt.png" width="70%"/>

## Requirements
[GIMP](https://www.gimp.org/), recommended GIMP version >= 2.10.  
In order for plugin to work correctly the GIMP's python module `gimpfu.py` has to be patched.  
The patch can be found [here](https://gitlab.gnome.org/GNOME/gimp/merge_requests/99//diffs).

## Installation
*Note: The installation guide is for GIMP version 2.10 or later.*  

   1. Download `gimp-file-mat.zip` from the [Releases](https://github.com/smlu/gimp-ijim/releases) page or download/clone this repository.
   2. Extract/copy the `file-mat` folder to GIMP's `plug-ins` folder:  
       **Windows**: `C:\Users\<USERNAME>\AppData\Roaming\GIMP\2.10\plug-ins`  
       *Make also sure you have GIMP installed with support for Python scripting.*  
       
       **Linux**: `/home/<USERNAME>/.config/GIMP/2.10/plug-ins`  
       **macOS**: `/Users/<USERNAME>/Library/Application Support/GIMP/2.10/plug-ins`

   *Note: If you can’t locate the `plug-ins` folder, open GIMP and go to Edit > Preferences > Folders > Plug-Ins and use one of the listed folders.*
   

## Usage
### Importing .mat file
To import `.mat` file into GIMP, go to *File > Open* then navigate to the folder containing `*.mat` file, select it and click *Open*.
*Note: For each texture in `.mat` file a new image window is opened in GIMP.*

<img src="https://github.com/smlu/gimp-ijim/blob/master/demo/imd.png" width="70%"/>
   
### Exporting .mat file
To export image as `.mat` file from GIMP, go to *File > Export As* then navigate to the folder where you want to export file, enter the file name with `*.mat` extension and click *Export*.  

A new dialog window will open where you have to select images to export as textures of `.mat` file and set additional export options.  

<img src="https://github.com/smlu/gimp-ijim/blob/master/demo/mated.png" width="40%"/>

*Note: If you are planning to use exported material in the game make sure to limit the length of file name to max 64 characters, including the `.mat` extension. See [File naming convention](https://github.com/smlu/blender-ijim#file-naming-convention) for more details.*  

