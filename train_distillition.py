import os
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch.cuda.amp import autocast, GradScaler

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
    print(f"Executing on: {device}")
    
    NUM_CLASSES = 3          
    BATCH_SIZE = 2           
    ACCUMULATION_STEPS = 8   
    ALPHA = 0.4              
    
    TOTAL_EPOCHS = 20
    RESUME_TRAINING = False  
    START_EPOCH = 1          
    
    DATA_DIR = "/content/dataset/images"
    ANNOTATION_FILE = "/content/dataset/annotations.json"
    
    # Cloud storage paths pointing to the EXCESS directory
    TEACHER_WEIGHTS = "/content/drive/MyDrive/EXCESS/lettuce_project/teacher_resnet101.pth"
    CHECKPOINT_DIR = "/content/drive/MyDrive/EXCESS/lettuce_project/checkpoints"
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    dataset = LettuceDetectionDataset(root_dir=DATA_DIR, annotation_file=ANNOTATION_FILE)
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, 
                            num_workers=2, collate_fn=collate_fn)
    
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
        
        for batch_idx, (images, targets) in enumerate(dataloader):
            images = list(img.to(device) for img in images)
            targets = [{k: v.to(device) for k, v in t.items()} for t in targets]
            img_tensor_stack = torch.stack(images)
            
            with autocast():
                with torch.no_grad():
                    teacher_features = teacher.backbone(img_tensor_stack)
                    
                student_features = student.backbone(img_tensor_stack)
                student_loss_dict = student(images, targets)
                standard_loss = sum(loss for loss in student_loss_dict.values())
                
                kd_loss = compute_feature_loss(teacher_features, student_features)
                total_loss = (standard_loss * ALPHA) + (kd_loss * (1.0 - ALPHA))
                total_loss = total_loss / ACCUMULATION_STEPS
            
            scaler.scale(total_loss).backward()
            epoch_loss += total_loss.item() * ACCUMULATION_STEPS
            
            if (batch_idx + 1) % ACCUMULATION_STEPS == 0 or (batch_idx + 1 == len(dataloader)):
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
                
        avg_epoch_loss = epoch_loss / len(dataloader)
        print(f"Epoch [{epoch+1}/{TOTAL_EPOCHS}] complete. Average Loss: {avg_epoch_loss:.4f}")
        
        checkpoint_path = os.path.join(CHECKPOINT_DIR, f"student_resnet18_epoch_{epoch+1}.pth")
        torch.save(student.state_dict(), checkpoint_path)
        print(f"Checkpoint saved to: {checkpoint_path}")

if __name__ == "__main__":
    run_training()