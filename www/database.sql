create table users (
    `id` varchar(50) not null,
    `email` varchar(50) not null,
    `passward` varchar(50) not null,
    
    `name` varchar(50) not null,  
    unique key `idx_email` (`email`), 
    primary key (`id`)
)