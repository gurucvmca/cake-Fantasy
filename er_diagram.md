# Cake Shop Entity-Relationship (ER) Diagram

This diagram represents the data models used in the Cake Shop application (MongoDB Collections).

```mermaid
erDiagram
    USER ||--o{ ORDER : "places"
    USER ||--o| CART : "manages"
    CAKE ||--o{ ORDER : "included_in"
    CAKE ||--o{ CART : "added_to"

    USER {
        string email "Unique Identifier"
        string password
        string role "admin/customer"
    }

    CAKE {
        objectId _id
        string name
        string description
        int price
        string image "URL/Path"
        string badge
        string badge_color
    }

    ORDER {
        objectId _id
        string user "References USER.email"
        string cake "Cake Name or List"
        int price "Total Paid"
        string payment "Payment Method"
    }

    CART {
        string id "References CAKE._id"
        string name
        int price
        int qty
        int total
    }
```

## Data Relationships

1. **User → Order (1:N)**: A single user can place multiple orders over time.
2. **Cake → Order (N:M)**: Logically, many cakes can be part of many orders. In this implementation, the order stores the cake names as a snapshot.
3. **User → Cart (1:1)**: Each active session user has one temporary cart stored in their session.
4. **Cake → Cart (1:N)**: Multiple cakes can be added to a single cart with specific quantities.
