# !/usr/bin/env python3

import os
import exifread


def log_exif_data(folder, output_file):
    """
    Reads all JPG files in 'folder', extracts EXIF data,
    and writes filename + EXIF tags to 'output_file'.
    """
    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        return

    with open(output_file, 'w', encoding='utf-8') as out:
        for filename in sorted(os.listdir(folder)):
            if filename.lower().endswith('.jpg'):
                file_path = os.path.join(folder, filename)

                with open(file_path, 'rb') as f:
                    tags = exifread.process_file(f)

                out.write(f"File: {filename}; ")
                for tag_name, tag_value in tags.items():
                    # if "JPEGThumbnail" in tag_name:
                    #     continue  # skip binary data
                    # out.write(f"{tag_name}: {tag_value}; ")

                    if "EXIF DateTimeOriginal" in tag_name:
                        out.write(f"{tag_name}: {tag_value}; ")
                out.write("\n")


if __name__ == "__main__":
    INPUT_FOLDER = "/home/mrbigheart/media/images"
    OUTPUT_TEXT_FILE = "/home/mrbigheart/media/exif_log.txt"

    log_exif_data(INPUT_FOLDER, OUTPUT_TEXT_FILE)
    print(f"EXIF info written to {OUTPUT_TEXT_FILE}")
