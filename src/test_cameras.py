import cv2

for index in [0, 1, 2]:

    print(f"\nOpening camera {index}...")

    camera = cv2.VideoCapture(index)

    if not camera.isOpened():

        print(f"❌ Could not open camera {index}")
        continue

    print(f"✅ Camera {index} opened")
    print("Press Q to close this camera and test the next one.")

    while True:

        success, frame = camera.read()

        if not success:
            print("❌ Could not read frame")
            break

        cv2.putText(
            frame,
            f"CAMERA INDEX: {index}",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        cv2.imshow(
            f"Testing Camera {index}",
            frame
        )

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()

print("\n🎉 Camera testing complete!")