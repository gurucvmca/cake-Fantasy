# Cake Shop Website Flowchart

This flowchart illustrates the user journey and page hierarchy of the Cake Shop website.

```mermaid
graph TD
    %% Entry Points
    Start((Start)) --> Login{Login / Signup}
    Login -- Signup --> Welcome
    Login -- Login --> Welcome
    Login -- Admin Login --> Admin[Admin Dashboard]

    %% Main Navigation
    Welcome[Welcome/Home Page] --> Menu[Browse Cake Menu]
    Welcome --> About[About Section]
    
    %% Product Interaction
    Menu --> Preview[3D Cake Preview]
    Menu --> AddCart[Add to Cart]
    Menu --> OrderDirect[Order Now]

    %% Cart & Checkout Flow
    AddCart --> Cart[View Cart]
    Cart --> Checkout[Checkout / Payment]
    OrderDirect --> Checkout
    
    %% Success
    Checkout -- Success --> SuccessPage[Order Success / Thank You]
    
    %% Styling
    style Start fill:#f9f,stroke:#333,stroke-width:4px
    style SuccessPage fill:#dfd,stroke:#333,stroke-width:2px
    style Admin fill:#fdd,stroke:#333,stroke-width:2px
    style Welcome fill:#dff,stroke:#333,stroke-width:2px
```

## Page Overview

| Page | Description |
| :--- | :--- |
| **Login/Signup** | User authentication module. |
| **Welcome** | The main landing page featuring a hero section and product catalog. |
| **3D Preview** | An interactive 3D model viewer for selected cakes. |
| **Cart** | Summary of items selected for purchase. |
| **Payment** | Secure checkout process. |
| **Success** | Confirmation of order placement. |
| **Admin** | Dashboard for managing inventory and orders (Admin only). |
