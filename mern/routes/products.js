const express = require("express");
const recordRoutes = express.Router();
const dbo = require("../db/conn");
const ObjectId = require("mongodb").ObjectId;

recordRoutes.route("/products").get(function(req, res) {
    let db_connect = dbo.getDb("warehouse");
    const { filter, sort } = req.query;

    let query = {};
    if (filter) {
      query = { name: { $regex: filter, $options: 'i' } };
    }

    let filterData = db_connect.collection("products").find(query);

    if (sort) {
      const sortOptions = {};
      sortOptions[sort] = 1; // 1 for ascending, -1 for descending
      filterData = filterData.sort(sortOptions);
    }

    filterData.toArray().then(result => {
        res.json(result);
    })  

});

recordRoutes.route("/products").post(function(req, response) {
    let db_connect = dbo.getDb("warehouse");

    // request input
    const newData = req.body;

    // Check if there is aleady a product with a name like this
    db_connect.collection("products").findOne({name: newData.name})
    .then(checkData => {
        if (checkData) {
            response.status(400).json({ error: 'Product name already exists' });
        } else {
            //Adding the new data
            db_connect.collection("products").insertOne(newData, function(err, res){
            if (err) throw err;
            response.json(res);
            });
        }
    })

    
});

recordRoutes.route("/products/:id").put(function(req, response) {
    let db_connect = dbo.getDb("warehouse");

    //Finding the id using the one give in the url
    const myqueryID = {_id: ObjectId(req.params.id)};

    const newValues = {$set: req.body};

    //Updating the query
    db_connect.collection("products").updateOne(myqueryID, newValues, function(err, res){
                if (err) throw err;
                console.log("1 document updated successfully");
                response.json(res);
            });
});

recordRoutes.route("/products/:id").delete(function(req, res) {
    let db_connect = dbo.getDb("warehouse");
    //Finding the id using the one give in the url
    const myquery = {_id: ObjectId(req.params.id)};

    //Deleting the query under the give id
    db_connect.collection("products").deleteOne(myquery, function(err, obj){
                if (err) throw err;
                console.log("1 document deleted");
                res.json(obj);
            });
});

recordRoutes.route("/report").get(function(req, res) {
    let db_connect = dbo.getDb("warehouse");
    db_connect.collection("products").aggregate([
        { $group: {_id: null, totalProducts: { $sum: 1}, totalValue: { $sum: { $multiply: ['$price', '$quantity']}}}}
    ]).toArray()
    .then( result => {
        res.json(result);
    })

    
});
module.exports = recordRoutes;
