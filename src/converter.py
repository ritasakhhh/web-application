from PIL import Image


def convert_png_to_jpeg(input_path, output_path):
    image = Image.open(input_path)
    image = image.convert("RGB")
    image.save(output_path, "JPEG")


def main():
    input_path = input("PNG file: ")
    output_path = input("JPEG file: ")

    convert_png_to_jpeg(
        input_path,
        output_path,
    )

    print("Conversion completed")


if __name__ == "__main__":
    main()
