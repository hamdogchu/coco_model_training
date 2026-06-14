import os
import json
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch.cuda.amp import autocast, GradScaler
from tqdm import tqdm  # <--- Added for real-time logging

from dataset import LettuceDetectionDataset, collate_fn
from models import get_student_model, get_teacher_model

def compute_feature_loss(teacher_features, student_features):
    loss = 0.0
    for key in ['0', '1', '2', '3']:
        t_feat = teacher_features[key].detach() 
        s_feat = student_features[key]
        loss += F.mse_loss(s_feat, t_feat)
    return loss

def run_training():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Executing Distillation on: {device}")
    
    # Cloud storage paths pointing to the EXCESS directory
    DATA_DIR = "/content/dataset/train"
    ANNOTATION_FILE = "/content/dataset/train/_annotations.coco.json"
    TEACHER_WEIGHTS = "/content/drive/MyDrive/EXCESS/lettuce_project/teacher_resnet101.pth"
    CHECKPOINT_DIR = "/content/drive/MyDrive/EXCESS/lettuce_project/checkpoints"
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    # --- DYNAMIC CLASS DETECTION ---
    with open(ANNOTATION_FILE, 'r') as f:
        coco_data = json.load(f)
        NUM_CLASSES = max([cat['id'] for cat in coco_data['categories']]) + 1
        print(f"Dynamically detected {NUM_CLASSES} total classes.")
    
    BATCH_SIZE = 2           
    ACCUMULATION_STEPS = 8   
    ALPHA = 0.4              
    
    # --- SESSION RECOVERY CONTROLS ---
    TOTAL_EPOCHS = 20
    RESUME_TRAINING = False  # Change to True to resume after a crash
    START_EPOCH = 1          # Change to the next epoch number if resuming

    dataset = LettuceDetectionDataset(root_dir=DATA_DIR, annotation_file=ANNOTATION_FILE)
    # Set num_workers=0 to prevent deadlocks
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, 
                            num_workers=0, collate_fn=collate_fn)
    
    teacher = get_teacher_model(NUM_CLASSES, pretrained_weights_path=TEACHER_WEIGHTS).to(device)
    student = get_student_model(NUM_CLASSES).to(device)
    
    if RESUME_TRAINING:
        latest_student_checkpoint = os.path.join(CHECKPOINT_DIR, f"student_resnet18_epoch_{START_EPOCH-1}.pth")
        print(f"Resuming training! Loading student weights from: {latest_student_checkpoint}")
        student.load_state_dict(torch.load(latest_student_checkpoint, map_location=device))
    
    optimizer = torch.optim.AdamW(student.parameters(), lr=5e-4, weight_decay=1e-4)
    scaler = GradScaler() 

    print(f"Starting epoch loop from Epoch {START_EPOCH}...")
    for epoch in range(START_EPOCH - 1, TOTAL_EPOCHS):
        student.train()
        optimizer.zero_grad()
        epoch_loss = 0.0
        
        # --- YOLO-STYLE LOGGING WRAPPER ---
        loop = tqdm(dataloader, leave=True)
        loop.set_description(f"Epoch [{epoch+1}/{TOTAL_EPOCHS}]")
        
        for batch_idx, (images, targets) in enumerate(loop):
            images = list(img.to(device) for img in images)
            targets = [{k: v.to(device) for k, v in t.items()} for t in targets]
            img_tensor_stack = torch.stack(images)
            
            with autocast():
                with torch.no_grad():
                    teacher_features = teacher.backbone(img_tensor_stack)
                    
                student_features = student.backbone(img_tensor_stack)
                student_loss_dict = student(images, targets)
                
                # Standard Faster R-CNN detection loss
                standard_loss = sum(loss for loss in student_loss_dict.values())
                
                # Feature map distillation loss
                kd_loss = compute_feature_loss(teacher_features, student_features)
                
                # Combined and scaled loss for backward pass
                total_loss = (standard_loss * ALPHA) + (kd_loss * (1.0 - ALPHA))
                scaled_loss = total_loss / ACCUMULATION_STEPS
            
            scaler.scale(scaled_loss).backward()
            epoch_loss += total_loss.item()
            
            if (batch_idx + 1) % ACCUMULATION_STEPS == 0 or (batch_idx + 1 == len(dataloader)):
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
                
            # --- REAL-TIME METRICS UPDATE ---
            # We display the unscaled losses so the numbers make intuitive sense
            loop.set_postfix(
                Total=f"{total_loss.item():.3f}", 
                Det=f"{standard_loss.item():.3f}", 
                KD=f"{kd_loss.item():.3f}"
            )
                
        print(f"Epoch [{epoch+1}/{TOTAL_EPOCHS}] Final Average Loss: {epoch_loss/len(dataloader):.4f}\n")
        
        checkpoint_path = os.path.join(CHECKPOINT_DIR, f"student_resnet18_epoch_{epoch+1}.pth")
        torch.save(student.state_dict(), checkpoint_path)
        print(f"Checkpoint saved to: {checkpoint_path}")

if __name__ == "__main__":
    run_training()