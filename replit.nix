{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.libpng
    pkgs.libjpeg
    pkgs.zlib
  ];
}
