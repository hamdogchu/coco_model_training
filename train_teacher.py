import os
import torch
from torch.utils.data import DataLoader
from dataset import LettuceDetectionDataset, collate_fn
from models import get_teacher_model

def train_teacher():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Training Teacher on: {device}")
    
    NUM_CLASSES = 3 
    BATCH_SIZE = 4       
    EPOCHS = 20
    
    # Local paths for the fast SSD
    DATA_DIR = "/content/dataset/images"
    ANNOTATION_FILE = "/content/dataset/annotations.json"
    
    # UPDATED: Target directory in Drive
    CHECKPOINT_DIR = "/content/drive/MyDrive/EXCESS/lettuce_project/"
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    
    dataset = LettuceDetectionDataset(root_dir=DATA_DIR, annotation_file=ANNOTATION_FILE)
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, 
                            num_workers=2, collate_fn=collate_fn)
    
    teacher = get_teacher_model(NUM_CLASSES, pretrained_weights_path=None).to(device)
    teacher.train()
    for param in teacher.parameters():
        param.requires_grad = True
        
    optimizer = torch.optim.AdamW(teacher.parameters(), lr=1e-4, weight_decay=1e-4)

    for epoch in range(EPOCHS):
        epoch_loss = 0.0
        
        for images, targets in dataloader:
            images = list(img.to(device) for img in images)
            targets = [{k: v.to(device) for k, v in t.items()} for t in targets]
            
            optimizer.zero_grad()
            loss_dict = teacher(images, targets)
            losses = sum(loss for loss in loss_dict.values())
            
            losses.backward()
            optimizer.step()
            
            epoch_loss += losses.item()
            
        print(f"Epoch [{epoch+1}/{EPOCHS}] Average Loss: {epoch_loss/len(dataloader):.4f}")
        
    final_path = os.path.join(CHECKPOINT_DIR, "teacher_resnet101.pth")
    torch.save(teacher.state_dict(), final_path)
    print(f"Teacher pre-training complete. Weights saved to {final_path}")

if __name__ == "__main__":
    train_teacher()