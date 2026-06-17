import cv2
import numpy as np
import onnxruntime as ort
import argparse

# Dictionary mapping your category IDs to names (Update these to match your Roboflow classes)
CLASS_NAMES = {
    1: "Anthracnose",
    2: "Aphid",
    3: "Bacterial Soft Rot",
    4: "Big Vein",
    5: "Downy Mildew",
    6: "Healthy",
    7: "Leaf Miner",
    8: "Lettuce Mosaic Virus",
    9: "Other Disease",
    10: "Other Pests",
    11: "Powdery Mildew",
    12: "Septoria Leaf Spot",
    13: "Thrip",
    14: "Tip Burn",
    15: "Whitefly"
}

def preprocess_image(image_path):
    """Replicates the PyTorch transforms purely using OpenCV and Numpy."""
    # Read image
    img = cv2.imread(image_path)
    original_h, original_w = img.shape[:2]
    
    # Convert BGR (OpenCV default) to RGB
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Resize to the 448x448 used during training
    img_resized = cv2.resize(img_rgb, (448, 448))
    
    # Normalize to [0.0, 1.0] and convert to float32
    img_normalized = img_resized.astype(np.float32) / 255.0
    
    # Transpose from (Height, Width, Channels) to (Channels, Height, Width)
    img_transposed = np.transpose(img_normalized, (2, 0, 1))
    
    # Add the batch dimension: (1, 3, 448, 448)
    input_tensor = np.expand_dims(img_transposed, axis=0)
    
    return img, input_tensor, original_w, original_h

def run_inference(onnx_path, image_path, confidence_threshold=0.5):
    print(f"Loading ONNX runtime session with {onnx_path}...")
    # Initialize the ONNX session using purely the CPU
    session = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
    
    # Prepare the image
    original_img, input_tensor, orig_w, orig_h = preprocess_image(image_path)
    
    print("Running inference...")
    # The name 'input_image' must match what we set in export_onnx.py
    outputs = session.run(None, {'input_image': input_tensor})
    
    # ONNX Faster R-CNN outputs a list of arrays: [boxes, labels, scores]
    boxes = outputs[0]
    labels = outputs[1]
    scores = outputs[2]
    
    # Calculate scale ratios to map 448x448 boxes back to original image dimensions
    scale_x = orig_w / 448.0
    scale_y = orig_h / 448.0
    
    detections_found = 0
    detected_summary = []
    
    for i in range(len(scores)):
        if scores[i] >= confidence_threshold:
            detections_found += 1
            
            # Map coordinates back to original size
            x1 = int(boxes[i][0] * scale_x)
            y1 = int(boxes[i][1] * scale_y)
            x2 = int(boxes[i][2] * scale_x)
            y2 = int(boxes[i][3] * scale_y)
            
            label_id = int(labels[i])
            score = float(scores[i])
            class_name = CLASS_NAMES.get(label_id, f"Unknown ({label_id})")
            
            # Add to our terminal summary list
            detected_summary.append(f"{class_name} (Confidence: {score*100:.1f}%)")
            
            # Draw the bounding box (Green)
            cv2.rectangle(original_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Draw the label background and text
            label_text = f"{class_name}: {score:.2f}"
            cv2.rectangle(original_img, (x1, y1 - 25), (x1 + len(label_text) * 12, y1), (0, 255, 0), -1)
            cv2.putText(original_img, label_text, (x1 + 5, y1 - 8), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    print(f"\n--- INFERENCE SUMMARY ---")
    print(f"Found {detections_found} valid targets above {confidence_threshold} confidence.")
    if detections_found > 0:
        print("Detected Classes:")
        for item in detected_summary:
            print(f"  * {item}")
    print("-------------------------\n")
    
    # Display the result on your screen
    cv2.imshow("Detection Results", original_img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    # Example usage: python resnet_test.py --model model.onnx --image test.jpg
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True, help="Path to ONNX file")
    parser.add_argument("--image", type=str, required=True, help="Path to test image")
    parser.add_argument("--conf", type=float, default=0.5, help="Confidence threshold")
    args = parser.parse_args()
    
    run_inference(args.model, args.image, args.conf)

# to run the script, use the command line:
# python resnet_test.py --model path_to_your_model.onnx --image path_to_your_test_image.jpg --conf 0.5