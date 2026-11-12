package require psfgen
resetpsf
readpsf 2KY5_snoopytag_built.psf
hmassrepart 3.024
writepsf 2KY5_snoopytag_hmr.psf
file copy -force 2KY5_snoopytag_built.pdb 2KY5_snoopytag_hmr.pdb
quit
