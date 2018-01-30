(function($){
  $(function(){

    $('.button-collapse').sideNav();
    $('.right-button-collapse').sideNav({
      edge: 'right'
    });



    $('.dropdown-button').dropdown({
      inDuration: 300,
      outDuration: 225,
      belowOrigin: true, // Displays dropdown below the button
      alignment: 'left' // Displays dropdown with edge aligned to the left of button
    });

  }); // end of document ready
})(jQuery); // end of jQuery name space